import os
import time
import requests
from typing import Any, Dict, Optional
from py_clob_client_v2 import ClobClient, ApiCreds, SignatureTypeV2, Side
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams, OrderArgs, OrderType
# from py_clob_client_v2.order_builder import
import logging
from web3 import Web3
from eth_account import Account
from py_clob_client_v2.config import get_contract_config
from py_builder_relayer_client.client import RelayClient
from py_builder_signing_sdk.config import BuilderApiKeyCreds, BuilderConfig
from bot.abi.ctf_abi import CTF_ABI
from bot.abi.usdc_abi import USDC_ABI
from bot.abi.pusd_abi import PUSD_ABI

logger = logging.getLogger(__name__)

# Constants
DEFAULT_GAS_PRICE = 200_000_000_000
GAS_LIMIT = 250_000
MAX_UINT256 = 2**256 - 1
TX_TIMEOUT = 300


class PolymarketClient:
    def __init__(self, private_key: str, proxy_url: str, chain_id: int = 137, is_mainnet: bool = True):
        self.chain_id = chain_id
        self.is_mainnet = is_mainnet
        self.private_key = private_key

        self.w3 = self._get_web3(is_mainnet)
        self.account = Account.from_key(private_key)
        self.address = self.account.address

        logger.info(f"EOA Address: {self.address}")

        self._check_pol_balance()

        self.contract_config = get_contract_config(chain_id)

        self.usdc = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_config.collateral),
            abi=USDC_ABI,
        )
        self.ctf = self.w3.eth.contract(
            address=Web3.to_checksum_address(self.contract_config.conditional_tokens),
            abi=CTF_ABI,
        )

        pusd_address = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
        self.pusd = self.w3.eth.contract(
            address=Web3.to_checksum_address(pusd_address),
            abi=PUSD_ABI,
        )
        logger.info(f"pUSD contract initialized at: {self.pusd.address}")

        # Initialize relayer client for deposit wallet
        self.relayer = self._init_relayer_client()

        self.deposit_wallet_address = self._get_or_deploy_deposit_wallet()
        logger.info(f"Deposit Wallet Address: {self.deposit_wallet_address}")

        # Initialize client with POLY_1271 signature type
        self.client = self._initialize_client_with_proxy(proxy_url)
        logger.info(f"Client initialized with POLY_1271, funder={self.deposit_wallet_address}")

    def _init_relayer_client(self) -> RelayClient:
        """Initialize the relayer client for deposit wallet management"""
        try:
            builder_config = BuilderConfig(
                local_builder_creds=BuilderApiKeyCreds(
                    key=os.environ.get("BUILDER_API_KEY", ""),
                    secret=os.environ.get("BUILDER_SECRET", ""),
                    passphrase=os.environ.get("BUILDER_PASS_PHRASE", ""),
                )
            )

            relayer_url = os.environ.get("RELAYER_URL", "https://relayer-v2.polymarket.com")
            relayer = RelayClient(
                relayer_url,
                self.chain_id,
                self.private_key,
                builder_config,
            )
            logger.info("Relayer client initialized successfully")
            return relayer
        except Exception as e:
            logger.error(f"Failed to initialize relayer client: {e}")
            raise

    def _get_or_deploy_deposit_wallet(self) -> str:
        """Get or deploy deposit wallet address for the current EOA"""
        try:
            # Step 1: Get the expected deposit wallet address (deterministic)
            # According to Polymarket docs, this method exists in RelayClient [citation:5]
            expected_address = self.relayer.get_expected_deposit_wallet()
            logger.info(f"Expected deposit wallet address: {expected_address}")

            # Step 2: Check if contract is already deployed
            code = self.w3.eth.get_code(Web3.to_checksum_address(expected_address))

            if len(code) <= 2:
                # Contract not deployed, deploy it
                logger.info("Deposit wallet not deployed, deploying now...")
                response = self.relayer.deploy_deposit_wallet()
                logger.info(f"Deploy deposit wallet response: {response}")

                # Wait for confirmation
                confirmed = response.wait()
                if not confirmed:
                    raise Exception("Deposit wallet deployment failed to confirm")

                # Wait a bit for propagation
                time.sleep(3)

                # Verify deployment
                code = self.w3.eth.get_code(Web3.to_checksum_address(expected_address))
                if len(code) <= 2:
                    raise Exception("Contract deployment verification failed")

                logger.info("Deposit wallet deployed and verified")
            else:
                logger.info("Deposit wallet already deployed")

            return expected_address

        except AttributeError as e:
            # If get_expected_deposit_wallet doesn't exist, we need to derive the address differently
            logger.warning(f"get_expected_deposit_wallet not available: {e}")
            logger.info("Attempting to derive deposit wallet address manually...")
            return self._derive_deposit_wallet_manually()
        except Exception as e:
            logger.error(f"Failed to get/deploy deposit wallet: {e}")
            raise

    def _derive_deposit_wallet_manually(self) -> str:
        """Manually derive deposit wallet address if relayer method is not available"""
        # According to Polymarket docs, the deposit wallet address is deterministic [citation:5]
        # It can be derived from the owner address and the deposit wallet factory contract

        # For now, we can get it by calling the bridge API to get deposit addresses
        try:
            response = requests.post(
                "https://bridge.polymarket.com/deposit",
                json={"address": self.address},
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            data = response.json()
            # The EVM deposit address is what we need
            evm_address = data.get("address", {}).get("evm")
            if evm_address:
                logger.info(f"Derived deposit wallet address from bridge API: {evm_address}")
                return evm_address
            else:
                raise Exception("No EVM address in response")
        except Exception as e:
            logger.error(f"Failed to derive deposit wallet address: {e}")
            logger.warning("Falling back to EOA address - this may not work for trading")
            return self.address

    def _verify_proxy_deployed(self) -> bool:
        """Verify that the proxy contract is deployed"""
        try:
            code = self.w3.eth.get_code(Web3.to_checksum_address(self.deposit_wallet_address))
            is_deployed = len(code) > 2
            logger.info(f"Proxy deployed: {is_deployed}, code length: {len(code)}")
            return is_deployed
        except Exception as e:
            logger.error(f"Failed to verify proxy deployment: {e}")
            return False

    def _initialize_client_with_proxy(self, proxy_url: str) -> ClobClient:
        """Initialize CLOB client with POLY_1271 signature type."""

        # --- 1. Получение или деплой deposit wallet ---
        if not self._verify_proxy_deployed():
            logger.warning("Proxy contract not deployed! Deploying now...")
            self._get_or_deploy_deposit_wallet()

        admin_client = ClobClient(
            host=proxy_url,
            chain_id=self.chain_id,
            key=self.private_key,
        )

        try:
            existing_keys = admin_client.get_api_keys()
            if existing_keys and hasattr(existing_keys, 'api_keys'):
                for key_info in existing_keys.api_keys:
                    logger.info(f"Deleting existing API key: {key_info.api_key}")
                    admin_client.delete_api_key(key_info.api_key)
            logger.info("Existing API keys cleared.")
        except Exception as e:
            # Если ключей нет, просто логируем ошибку
            logger.info(f"No existing keys to delete or error: {e}")

        temp_client = ClobClient(
            host=proxy_url,
            chain_id=self.chain_id,
            key=self.private_key,
            signature_type=SignatureTypeV2.POLY_1271,
            funder=self.deposit_wallet_address,
        )

        try:
            creds = temp_client.create_or_derive_api_key()
            logger.info(f"SUCCESS: New API Key created for deposit wallet: {self.deposit_wallet_address}")
        except Exception as e:
            logger.error(f"Failed to create new API key: {e}")
            raise

        client = ClobClient(
            host=proxy_url,
            chain_id=self.chain_id,
            key=self.private_key,
            creds=creds,
            signature_type=SignatureTypeV2.POLY_1271,
            funder=self.deposit_wallet_address,
        )

        ok = client.get_ok()
        logger.info(f"Health check: {ok}")
        if ok != "OK":
            raise Exception("CLOB server health check failed")

        try:
            balance = client.get_balance_allowance(params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL))
            logger.info("Balance check successful - authentication is working!")
        except Exception as e:
            logger.error(f"CRITICAL: Balance check failed even after key reset. Error: {e}")

        return client

    def sync_clob_balance(self):
        """Sync on-chain balance with CLOB - required after deposits/approvals"""
        try:
            result = self.client.update_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            logger.info(f"Balance synced successfully: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to sync balance: {e}")
            raise

    def _check_pol_balance(self):
        try:
            pol_balance = self.w3.eth.get_balance(self.account.address)
            pol_balance_formatted = pol_balance / 1e18

            if pol_balance_formatted < 0.05:
                logger.warning(f"Low POL balance: {pol_balance_formatted:.6f} POL. Need at least 0.05 POL for gas fees.")
            else:
                logger.info(f"POL balance: {pol_balance_formatted:.6f} POL")

            return pol_balance
        except Exception as e:
            logger.error(f"Failed to check POL balance: {e}")
            return 0

    def _get_gas_price(self) -> int:
        try:
            current_gas_price = self.w3.eth.gas_price
            current_gwei = current_gas_price / 1e9

            if current_gwei < 100:
                gas_price = int(current_gas_price * 1.5)
            elif current_gwei < 300:
                gas_price = int(current_gas_price * 1.3)
            else:
                gas_price = int(current_gas_price * 1.2)

            max_gas_price = 800_000_000_000

            if gas_price > max_gas_price:
                gas_price = max_gas_price
                logger.warning(f"Gas price capped at {max_gas_price / 1e9:.2f} Gwei")

            logger.info(f"Gas price - Current: {current_gwei:.2f} Gwei, Using: {gas_price / 1e9:.2f} Gwei")
            return gas_price

        except Exception as e:
            logger.warning(f"Failed to get dynamic gas price, using default: {e}")
            return DEFAULT_GAS_PRICE

    def _wait_for_transaction(self, tx_hash, timeout: int = TX_TIMEOUT, poll_latency: int = 5):
        start_time = time.time()
        time.sleep(3)

        while time.time() - start_time < timeout:
            try:
                receipt = self.w3.eth.get_transaction_receipt(tx_hash)

                if receipt is not None:
                    if receipt['status'] == 1:
                        logger.info(f"Transaction confirmed in block {receipt['blockNumber']}")
                        return receipt
                    else:
                        logger.error("Transaction failed with status 0")
                        return None

                try:
                    tx = self.w3.eth.get_transaction(tx_hash)
                    if tx:
                        elapsed = int(time.time() - start_time)
                        logger.info(f"Transaction in mempool for {elapsed}s, waiting...")
                except Exception:
                    pass

                time.sleep(poll_latency)

            except Exception as e:
                logger.warning(f"Error checking transaction status: {e}")
                time.sleep(poll_latency)

        logger.error(f"Transaction not confirmed after {timeout} seconds")
        return None

    def _get_web3(self, is_mainnet: bool) -> Web3:
        rpc_token = os.environ.get("RPC_TOKEN")

        if is_mainnet:
            if rpc_token:
                rpc_url = f"https://polygon-mainnet.g.alchemy.com/v2/{rpc_token}"
            else:
                rpc_url = "https://polygon-rpc.com"
                logger.warning("Using public RPC for Mainnet")
        else:
            if rpc_token:
                rpc_url = f"https://polygon-amoy.g.alchemy.com/v2/{rpc_token}"
            else:
                rpc_url = "https://rpc-amoy.polygon.technology"
                logger.warning("Using public RPC for Amoy")

        logger.info(f"Using RPC: {rpc_url[:50]}...")
        w3 = Web3(Web3.HTTPProvider(rpc_url))

        if not w3.is_connected():
            logger.error("Failed to connect to RPC")
            raise ConnectionError("Cannot connect to RPC")

        return w3

    def get_markets(self, limit: int = 20):
        try:
            return self.client.get_markets()
        except Exception as e:
            logger.error(f"Failed to get markets: {e}")
            return []

    def get_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        try:
            markets = self.get_markets()
            for market in markets:
                if market.get('slug') == slug:
                    return market
            logger.warning(f"Market with slug '{slug}' not found.")
            return None
        except Exception as e:
            logger.error(f"Failed to get market by slug: {e}")
            return None

    def get_order_book(self, token_id: str):
        try:
            return self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Failed to get order book: {e}")
            return {}

    def place_order(self, token_id: str, price: float, size: float, side: str, order_type: str = "GTC"):
        """
        Place an order on Polymarket

        Args:
            token_id: The token ID to trade
            price: Price per share (0-1)
            size: Size in USDC (will be converted to wei)
            side: "BUY" or "SELL"
            order_type: "GTC" (Good 'til Cancelled) or "FOK" (Fill or Kill)
        """
        try:
            # Convert size to integer (USDC has 6 decimals)
            size_in_wei = int(size * 1_000_000)

            # Convert side to enum
            side_enum = Side.BUY if side.upper() == "BUY" else Side.SELL

            # Create order args
            order_args = OrderArgs(
                token_id=token_id,
                price=price,
                size=size_in_wei,
                side=side_enum,
            )

            # Set order type
            order_type_enum = OrderType.GTC if order_type.upper() == "GTC" else OrderType.FOK

            # Create and post order
            signed_order = self.client.create_order(order_args)
            response = self.client.post_order(signed_order, order_type_enum)

            logger.info(f"Order placed successfully: {response}")
            return response

        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            raise

    def get_orders(self):
        try:
            return self.client.get_open_orders()
        except Exception as e:
            logger.error(f"Failed to get orders: {e}")
            return []

    def cancel_order(self, order_id: str):
        try:
            return self.client.cancel_order(order_id)
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            raise

    def cancel_all(self):
        try:
            return self.client.cancel_all()
        except Exception as e:
            logger.error(f"Failed to cancel all orders: {e}")
            raise

    def get_balance_allowance(self):
        """Get balance and allowance from CLOB"""
        try:
            result = self.client.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )
            logger.info(f"Balance/Allowance: {result}")
            return result
        except Exception as e:
            logger.error(f"Failed to get balance: {e}")
            return None

    def approve_usdc(self, amount: int = None):
        """Approve USDC for CTF and Exchange contracts"""
        try:
            self.clear_pending_transactions()

            if amount is None:
                amount = MAX_UINT256

            logger.info(f"Approving USDC: amount={amount}")

            pol_balance = self.w3.eth.get_balance(self.account.address)
            if pol_balance < 0.02 * 1e18:
                raise Exception(f"Insufficient POL for gas: {pol_balance / 1e18:.6f} POL")

            allowance_ctf = self.usdc.functions.allowance(self.account.address, self.contract_config.conditional_tokens).call()
            allowance_exchange = self.usdc.functions.allowance(self.account.address, self.contract_config.exchange).call()

            logger.info(f"Current allowance - CTF: {allowance_ctf}, Exchange: {allowance_exchange}")

            nonce = self.w3.eth.get_transaction_count(self.account.address)
            tx_hashes = []

            if allowance_ctf < amount:
                logger.info("Approving CTF contract...")
                gas_price = self._get_gas_price()
                gas_price = int(gas_price * 1.3)

                txn = self.usdc.functions.approve(
                    self.contract_config.conditional_tokens, amount
                ).build_transaction({
                    "from": self.account.address,
                    "gasPrice": gas_price,
                    "gas": GAS_LIMIT,
                    "nonce": nonce,
                    "chainId": self.chain_id,
                })

                signed = self.account.sign_transaction(txn)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                logger.info(f"CTF approval tx sent: {tx_hash.hex()}")

                receipt = self._wait_for_transaction(tx_hash)
                if receipt:
                    logger.info("CTF approval confirmed")
                    tx_hashes.append(tx_hash.hex())
                    nonce += 1

            if allowance_exchange < amount:
                logger.info("Approving Exchange contract...")
                gas_price = self._get_gas_price()
                gas_price = int(gas_price * 1.3)

                txn = self.usdc.functions.approve(
                    self.contract_config.exchange,
                    amount
                ).build_transaction({
                    "from": self.account.address,
                    "gasPrice": gas_price,
                    "gas": GAS_LIMIT,
                    "nonce": nonce,
                    "chainId": self.chain_id,
                })

                signed = self.account.sign_transaction(txn)
                tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                logger.info(f"Exchange approval tx sent: {tx_hash.hex()}")

                receipt = self._wait_for_transaction(tx_hash)
                if receipt:
                    logger.info("Exchange approval confirmed")
                    tx_hashes.append(tx_hash.hex())

            logger.info(f"USDC approvals completed successfully. TXs: {tx_hashes}")

            # Sync balance with CLOB after approvals
            if tx_hashes:
                time.sleep(2)
                self.sync_clob_balance()

            return tx_hashes

        except Exception as e:
            logger.error(f"Failed to approve USDC: {e}")
            raise

    def approve_conditional_tokens(self):
        """Approve Conditional Tokens for Exchange"""
        try:
            self.clear_pending_transactions()

            logger.info("Approving Conditional Tokens for Exchange...")

            pol_balance = self.w3.eth.get_balance(self.account.address)
            if pol_balance < 0.02 * 1e18:
                raise Exception(f"Insufficient POL for gas: {pol_balance / 1e18:.6f} POL")

            is_approved = self.ctf.functions.isApprovedForAll(self.account.address, self.contract_config.exchange).call()

            if is_approved:
                logger.info("Conditional Tokens already approved")
                return True

            nonce = self.w3.eth.get_transaction_count(self.account.address)
            gas_price = self._get_gas_price()
            gas_price = int(gas_price * 1.3)

            txn = self.ctf.functions.setApprovalForAll(self.contract_config.exchange, True).build_transaction({
                "from": self.account.address,
                "gasPrice": gas_price,
                "gas": GAS_LIMIT,
                "nonce": nonce,
                "chainId": self.chain_id,
            })

            signed = self.account.sign_transaction(txn)
            tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
            logger.info(f"Conditional Tokens approval tx sent: {tx_hash.hex()}")

            receipt = self._wait_for_transaction(tx_hash)
            if receipt:
                logger.info("Conditional Tokens approval confirmed")
                return tx_hash.hex()
            else:
                raise Exception("Transaction not confirmed")

        except Exception as e:
            logger.error(f"Failed to approve Conditional Tokens: {e}")
            raise

    def clear_pending_transactions(self):
        """Clear stuck transactions"""
        try:
            logger.info("Checking for stuck transactions...")

            current_nonce = self.w3.eth.get_transaction_count(self.account.address)
            pending_nonce = self.w3.eth.get_transaction_count(self.account.address, 'pending')

            logger.info(f"Current nonce: {current_nonce}, Pending nonce: {pending_nonce}")

            if pending_nonce > current_nonce:
                logger.warning(f"Found {pending_nonce - current_nonce} stuck transaction(s)")

                for nonce in range(current_nonce, pending_nonce):
                    try:
                        gas_price = self._get_gas_price()
                        gas_price = int(gas_price * 2)

                        tx = {
                            'to': self.account.address,
                            'value': 0,
                            'gas': 21000,
                            'gasPrice': gas_price,
                            'nonce': nonce,
                            'chainId': self.chain_id,
                        }

                        signed = self.account.sign_transaction(tx)
                        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
                        logger.info(f"Cleared stuck tx with nonce {nonce}: {tx_hash.hex()}")
                        time.sleep(2)

                    except Exception as e:
                        logger.error(f"Failed to clear nonce {nonce}: {e}")
                logger.info("Waiting for stuck transactions to clear...")
                time.sleep(10)
                return True
            else:
                logger.info("No stuck transactions found")
                return False
        except Exception as e:
            logger.error(f"Failed to clear pending transactions: {e}")
            return False

    def get_wallet_balance(self):
        """Get complete wallet balance information"""
        try:
            usdc_balance = self.usdc.functions.balanceOf(self.account.address).call()
            pol_balance = self.w3.eth.get_balance(self.account.address)

            api_result = self.client.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )

            allowances = api_result.get('allowances', {}) if api_result else {}
            platform_balance = int(api_result.get('balance', '0')) if api_result else 0

            return {
                'usdc_balance': usdc_balance,
                'usdc_balance_formatted': usdc_balance / 1e6,
                'platform_balance': platform_balance,
                'platform_balance_formatted': platform_balance / 1e6,
                'pol_balance': pol_balance,
                'pol_balance_formatted': pol_balance / 1e18,
                'exchange_allowance': allowances.get(self.contract_config.exchange, '0'),
                'conditional_tokens_approved': self.ctf.functions.isApprovedForAll(
                    self.account.address,
                    self.contract_config.exchange
                ).call(),
                'deposit_wallet': self.deposit_wallet_address
            }
        except Exception as e:
            logger.error(f"Failed to get wallet balance: {e}")
            return None
