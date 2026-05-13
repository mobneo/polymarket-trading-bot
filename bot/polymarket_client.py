import os
import time
from typing import Any, Dict, Optional
from py_clob_client_v2 import ClobClient, ApiCreds
from py_clob_client_v2.clob_types import AssetType, BalanceAllowanceParams, OrderArgs, OrderType
import logging
from web3 import Web3
from eth_account import Account
from py_clob_client_v2.config import get_contract_config
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

        self.w3 = self._get_web3(is_mainnet)
        self.account = Account.from_key(private_key)

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

        # pUSD contract (Polymarket USD)
        pusd_address = "0xC011a7E12a19f7B1f670d46F03B03f3342E82DFB"
        self.pusd = self.w3.eth.contract(
            address=Web3.to_checksum_address(pusd_address),
            abi=PUSD_ABI,
        )
        logger.info(f"pUSD contract initialized at: {self.pusd.address}")

        self.client = ClobClient(
            host=proxy_url,
            key=private_key,
            chain_id=chain_id,
        )

        try:
            creds = self.client.create_or_derive_api_key()
            logger.info("API credentials generated successfully")

            self.client = ClobClient(
                host=proxy_url,
                key=private_key,
                chain_id=chain_id,
                creds=creds,
            )
            logger.info("Polymarket client initialized with full authentication")
        except Exception as e:
            logger.error(f"Failed to create API credentials: {e}")
            raise

    def _check_pol_balance(self):
        try:
            pol_balance = self.w3.eth.get_balance(self.account.address)
            pol_balance_formatted = pol_balance / 1e18

            if pol_balance_formatted < 0.01:
                logger.warning(f"Low POL balance: {pol_balance_formatted:.6f} POL. Need at least 0.01 POL for gas fees.")
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

    def get_market_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """Finds a market by its slug."""
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

    def get_order_book(self, token_id: str):
        try:
            return self.client.get_order_book(token_id)
        except Exception as e:
            logger.error(f"Failed to get order book: {e}")
            return {}

    def place_order(self, token_id: str, price: float, size: float, side: str):
        try:
            order = OrderArgs(price=price, size=size, side=side, token_id=token_id)
            signed = self.client.create_order(order)
            return self.client.post_order(signed)
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
            return tx_hashes

        except Exception as e:
            logger.error(f"Failed to approve USDC: {e}")
            raise

    def approve_pusd_for_ctf(self, amount: int = None):
        """Approve CTF contract to spend pUSD on your behalf"""
        try:
            self.clear_pending_transactions()

            if amount is None:
                amount = MAX_UINT256

            logger.info(f"Approving pUSD for CTF contract: amount={amount}")
            logger.info(f"pUSD contract: {self.pusd.address}")
            logger.info(f"CTF contract: {self.contract_config.conditional_tokens}")

            pol_balance = self.w3.eth.get_balance(self.account.address)
            if pol_balance < 0.02 * 1e18:
                raise Exception(f"Insufficient POL for gas: {pol_balance / 1e18:.6f} POL")

            current_allowance = self.pusd.functions.allowance(
                self.account.address,
                self.contract_config.conditional_tokens
            ).call()

            logger.info(f"Current pUSD allowance for CTF: {current_allowance}")

            if current_allowance >= amount:
                logger.info("pUSD allowance already sufficient")
                return True

            nonce = self.w3.eth.get_transaction_count(self.account.address)
            gas_price = self._get_gas_price()
            gas_price = int(gas_price * 1.3)
            logger.info(f"Using gas price: {gas_price / 1e9:.2f} Gwei")

            txn = self.pusd.functions.approve(
                self.contract_config.conditional_tokens,
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
            logger.info(f"pUSD approval tx sent: {tx_hash.hex()}")

            receipt = self._wait_for_transaction(tx_hash)
            if receipt:
                logger.info("pUSD approval confirmed")
                return tx_hash.hex()
            else:
                raise Exception("pUSD approval not confirmed")

        except Exception as e:
            logger.error(f"Failed to approve pUSD: {e}")
            raise

    def approve_pusd_for_exchange(self, amount: int = None):
        """Approve Exchange contract to spend pUSD on your behalf"""
        try:
            self.clear_pending_transactions()

            if amount is None:
                amount = MAX_UINT256

            logger.info(f"Approving pUSD for Exchange contract: amount={amount}")
            logger.info(f"pUSD contract: {self.pusd.address}")
            logger.info(f"Exchange contract: {self.contract_config.exchange}")

            pol_balance = self.w3.eth.get_balance(self.account.address)
            if pol_balance < 0.02 * 1e18:
                raise Exception(f"Insufficient POL for gas: {pol_balance / 1e18:.6f} POL")

            current_allowance = self.pusd.functions.allowance(
                self.account.address,
                self.contract_config.exchange
            ).call()

            logger.info(f"Current pUSD allowance for Exchange: {current_allowance}")

            if current_allowance >= amount:
                logger.info("pUSD allowance for Exchange already sufficient")
                return True

            nonce = self.w3.eth.get_transaction_count(self.account.address)
            gas_price = self._get_gas_price()
            gas_price = int(gas_price * 1.3)

            txn = self.pusd.functions.approve(
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
            logger.info(f"pUSD exchange approval tx sent: {tx_hash.hex()}")

            receipt = self._wait_for_transaction(tx_hash)
            if receipt:
                logger.info("pUSD exchange approval confirmed")
                return tx_hash.hex()
            else:
                raise Exception("pUSD exchange approval not confirmed")

        except Exception as e:
            logger.error(f"Failed to approve pUSD for Exchange: {e}")
            raise

    def approve_pusd_all(self, amount: int = None):
        """Approve both CTF and Exchange contracts to spend pUSD"""
        try:
            logger.info("Setting up all pUSD approvals...")

            ctf_tx = self.approve_pusd_for_ctf(amount)
            exchange_tx = self.approve_pusd_for_exchange(amount)

            logger.info("All pUSD approvals completed successfully")
            return {
                "ctf_approval": ctf_tx,
                "exchange_approval": exchange_tx
            }
        except Exception as e:
            logger.error(f"Failed to setup pUSD approvals: {e}")
            raise

    def approve_conditional_tokens(self):
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

    def setup_all_approvals(self, usdc_amount: int = None):
        try:
            logger.info("Setting up all approvals...")

            usdc_txs = self.approve_usdc(usdc_amount)
            ctf_tx = self.approve_conditional_tokens()

            logger.info("All approvals completed successfully")
            return {
                "usdc_approvals": usdc_txs,
                "ctf_approval": ctf_tx
            }
        except Exception as e:
            logger.error(f"Failed to setup approvals: {e}")
            raise

    def clear_pending_transactions(self):
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
        try:
            usdc_balance = self.usdc.functions.balanceOf(self.account.address).call()
            pusd_balance = self.pusd.functions.balanceOf(self.account.address).call()
            pol_balance = self.w3.eth.get_balance(self.account.address)

            api_result = self.client.get_balance_allowance(
                params=BalanceAllowanceParams(asset_type=AssetType.COLLATERAL)
            )

            allowances = api_result.get('allowances', {})
            platform_balance = int(api_result.get('balance', '0')) if api_result else 0

            # Get pUSD allowances
            pusd_ctf_allowance = self.pusd.functions.allowance(
                self.account.address,
                self.contract_config.conditional_tokens
            ).call()
            pusd_exchange_allowance = self.pusd.functions.allowance(
                self.account.address,
                self.contract_config.exchange
            ).call()

            return {
                'usdc_balance': usdc_balance,
                'usdc_balance_formatted': usdc_balance / 1e6,
                'pusd_balance': pusd_balance,
                'pusd_balance_formatted': pusd_balance / 1e6,
                'platform_balance': platform_balance,
                'platform_balance_formatted': platform_balance / 1e6,
                'pol_balance': pol_balance,
                'pol_balance_formatted': pol_balance / 1e18,
                'api_balance': api_result.get('balance', '0'),
                'allowances': allowances,
                'exchange_allowance': allowances.get(self.contract_config.exchange, '0'),
                'pusd_ctf_allowance': pusd_ctf_allowance,
                'pusd_ctf_allowance_formatted': "∞" if pusd_ctf_allowance == MAX_UINT256 else f"{pusd_ctf_allowance / 1e6:.2f}",
                'pusd_exchange_allowance': pusd_exchange_allowance,
                'pusd_exchange_allowance_formatted': "∞" if pusd_exchange_allowance == MAX_UINT256 else f"{pusd_exchange_allowance / 1e6:.2f}",
                'conditional_tokens_approved': self.ctf.functions.isApprovedForAll(
                    self.account.address,
                    self.contract_config.exchange
                ).call()
            }
        except Exception as e:
            logger.error(f"failed to get wallet balance: {e}")
            return None
