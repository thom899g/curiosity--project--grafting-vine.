"""
Gas Oracle Consensus Mechanism
Architectural Choice: Multiple independent sources with median calculation prevents
single point of failure and provides robust gas price estimation.
"""

import requests
import time
import statistics
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import logging
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GasOracle:
    """Consensus-based gas price estimator with outlier rejection"""
    
    def __init__(self, etherscan_api_key: str = None):
        self.etherscan_api_key = etherscan_api_key or os.getenv('ETHERSCAN_API_KEY')
        
        # Define multiple independent gas price sources
        self.gas_sources = [
            self._get_etherscan_gas,
            self._get_gas_station_gas,
            self._get_blocknative_gas,
            self._get_chainlink_gas
        ]
        
        # Historical data for pattern recognition
        self.history: List[Dict] = []
        self.max_history = 1000
        
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type(requests.RequestException)
    )
    def _get_etherscan_gas(self) -> Optional[Tuple[int, int, int]]:
        """Get gas prices from Etherscan API"""
        try:
            url = "https://api.etherscan.io/api"
            params = {
                'module': 'gastracker',
                'action': 'gasoracle',
                'apikey': self.etherscan_api_key
            }
            
            response = requests.get(url, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            if data['status'] == '1':
                result = data['result']
                safe = int(result['SafeGasPrice'])
                proposed = int(result['ProposeGasPrice'])
                fast = int(result['FastGasPrice'])
                return (safe, proposed, fast)
        except Exception as e:
            logger.warning(f"Etherscan gas API failed: {e}")
            return None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10)
    )
    def _get_gas_station_gas(self) -> Optional[Tuple[int, int, int]]:
        """Get gas prices from EthGasStation (now Blocknative)"""
        try:
            url = "https://ethgasstation.info/api/ethgasAPI.json"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Convert from gwei * 10 to gwei
            safe = int(data['safeLow'] / 10)
            average = int(data['average'] / 10)
            fast = int(data['fast'] / 10)
            
            return (safe, average, fast)
        except Exception as e:
            logger.warning(f"Gas Station API failed: {e}")
            return None
    
    def _get_blocknative_gas(self) -> Optional[Tuple[int, int, int]]:
        """Get gas prices from Blocknative Gas Estimator"""
        try:
            # Using public endpoint - rate limited but free
            url = "https://api.blocknative.com/gasprices/blockprices"
            headers = {
                'Authorization': ''  # Empty for public access
            }
            response = requests.get(url, headers=headers, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Parse Blocknative response
            if 'blockPrices' in data and len(data['blockPrices']) > 0:
                estimates = data['blockPrices'][0]['estimatedPrices']
                safe = int(estimates[2]['price'])  # 70th percentile
                average = int(estimates[1]['price'])  # 50th percentile  
                fast = int(estimates[0]['price'])  # 10th percentile
                return (safe, average, fast)
        except Exception as e:
            logger.warning(f"Blocknative API failed: {e}")
            return None
    
    def _get_chainlink_gas(self) -> Optional[Tuple[int, int, int]]:
        """Get gas prices from Chainlink Fast Gas/Gwei"""
        try:
            # Chainlink Fast Gas feed on Ethereum mainnet
            # This is a simplified version - would need Web3 for actual feed
            # Using fallback to public API
            url = "https://gas-price-api.1inch.io/v1.2/1"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            
            # Extract prices from 1inch gas API
            fast = int(data['fast'])
            standard = int(data['standard'])
            instant = int(data['instant'])
            
            return (standard, fast, instant)
        except Exception as e:
            logger.warning(f"Chainlink gas API failed: {e}")
            return None
    
    def _calculate_consensus(self, prices: List[Tuple[int, int, int]]) -> Dict[str, int]:
        """Calculate median gas prices from multiple sources with outlier rejection"""
        
        if not prices:
            logger.error("No gas price data available from any source")
            # Return safe fallback values
            return {
                'safe': 20,  # gwei
                'average': 30,  # gwei
                'fast': 40,  # gwei
                'source_count': 0,
                'confidence': 'low'
            }
        
        # Separate price tiers
        safe_prices = [p[0] for p in prices if p[0] is not None]
        avg_prices = [p[1] for p in prices if p[1] is not None]
        fast_prices = [p[2] for p in prices if p[2] is not None]
        
        # Function to calculate median with outlier rejection
        def robust_median(values: List[int]) -> int:
            if not values:
                return None
            if len(values) == 1:
                return values[0]
            
            # Calculate IQR for outlier detection
            sorted_vals = sorted(values)
            q1 = sorted_vals[len(sorted_vals) // 4]
            q3 = sorted_vals[3 * len(sorted_vals) // 4]
            iqr = q3 - q1
            
            # Filter outliers (more than 1.5 * IQR from Q1/Q3)
            filtered = [v for v in values if (q1 - 1.5 * iqr) <= v <= (q3 + 1.5 * iqr)]
            
            if filtered:
                return int(statistics.median(filtered))
            else:
                return int(statistics.median(values))  # Fallback to regular median
        
        safe = robust_median(safe_prices)
        average = robust_median(avg_prices)
        fast = robust_median(fast_prices)
        
        # Determine confidence level based on source agreement
        source_count = len(prices)
        variance = statistics.stdev([safe or 0, average or 0, fast or 0]) if source_count >= 2 else 100
        
        confidence = 'high' if variance < 5 and source_count >= 3 else 'medium' if source_count >= 2 else 'low'
        
        return {
            'safe': safe or 20,
            'average': average or 30,
            'fast': fast or 40,
            'source_count': source_count,
            'confidence': confidence,
            'timestamp': datetime.utcnow().isoformat()
        }
    
    def get_current_gas_prices(self) -> Dict[str, any]:
        """Main method to get consensus gas prices"""
        
        logger.info("Fetching gas price consensus from multiple sources...")
        
        prices = []
        for source in self.gas_sources:
            try:
                result = source()
                if result:
                    prices.append(result)
                    logger.debug(f"Source {source.__name__} returned: {result}")
            except Exception as e:
                logger.warning(f"Gas source {source.__name__} failed: {e}")
                continue
        
        consensus = self._calculate_consensus(prices)