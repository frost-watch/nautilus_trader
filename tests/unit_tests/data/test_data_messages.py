# -------------------------------------------------------------------------------------------------
#  Copyright (C) 2015-2021 Nautech Systems Pty Ltd. All rights reserved.
#  https://nautechsystems.io
#
#  Licensed under the GNU Lesser General Public License Version 3.0 (the "License");
#  You may not use this file except in compliance with the License.
#  You may obtain a copy of the License at https://www.gnu.org/licenses/lgpl-3.0.en.html
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
# -------------------------------------------------------------------------------------------------

import unittest

from nautilus_trader.common.clock import TestClock
from nautilus_trader.common.uuid import UUIDFactory
from nautilus_trader.data.base import DataType
from nautilus_trader.data.messages import DataRequest
from nautilus_trader.data.messages import DataResponse
from nautilus_trader.data.messages import Subscribe
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.tick import QuoteTick

BINANCE = Venue("BINANCE")
IDEALPRO = Venue("IDEALPRO")


class DataMessageTests(unittest.TestCase):

    def setUp(self):
        # Fixture Setup
        self.clock = TestClock()
        self.uuid_factory = UUIDFactory()

    def test_data_command_str_and_repr(self):
        # Arrange
        # Act
        handler = [].append
        command_id = self.uuid_factory.generate()

        command = Subscribe(
            provider=BINANCE.value,
            data_type=DataType(str, {"type": "newswire"}),  # str data type is invalid
            handler=handler,
            command_id=command_id,
            command_timestamp=self.clock.utc_now(),
        )

        # Assert
        self.assertEqual("Subscribe(<str> {'type': 'newswire'})", str(command))
        self.assertEqual(f"Subscribe(provider=BINANCE, data_type=<str> {{'type': 'newswire'}}, handler={repr(handler)}, id={command_id}, timestamp=1970-01-01 00:00:00+00:00)", repr(command))

    def test_data_request_message_str_and_repr(self):
        # Arrange
        # Act
        handler = [].append
        request_id = self.uuid_factory.generate()

        request = DataRequest(
            provider=BINANCE.value,
            data_type=DataType(str, metadata={  # str data type is invalid
                "Symbol": Symbol("SOMETHING", Venue("RANDOM")),
                "FromDateTime": None,
                "ToDateTime": None,
                "Limit": 1000,
            }),
            callback=handler,
            request_id=request_id,
            request_timestamp=self.clock.utc_now(),
        )

        # Assert
        self.assertEqual("DataRequest(<str> {'Symbol': Symbol('SOMETHING.RANDOM'), 'FromDateTime': None, 'ToDateTime': None, 'Limit': 1000})", str(request))
        self.assertEqual(f"DataRequest(provider=BINANCE, data_type=<str> {{'Symbol': Symbol('SOMETHING.RANDOM'), 'FromDateTime': None, 'ToDateTime': None, 'Limit': 1000}}, callback={repr(handler)}, id={request_id}, timestamp=1970-01-01 00:00:00+00:00)", repr(request))

    def test_data_response_message_str_and_repr(self):
        # Arrange
        # Act
        correlation_id = self.uuid_factory.generate()
        response_id = self.uuid_factory.generate()

        response = DataResponse(
            provider=BINANCE.value,
            data_type=DataType(QuoteTick, metadata={"Symbol": Symbol("AUD/USD", IDEALPRO)}),
            data=[],
            correlation_id=correlation_id,
            response_id=response_id,
            response_timestamp=self.clock.utc_now(),
        )

        # Assert
        self.assertEqual("DataResponse(<QuoteTick> {'Symbol': Symbol('AUD/USD.IDEALPRO')})", str(response))
        self.assertEqual(f"DataResponse(provider=BINANCE, data_type=<QuoteTick> {{'Symbol': Symbol('AUD/USD.IDEALPRO')}}, correlation_id={correlation_id}, id={response_id}, timestamp=1970-01-01 00:00:00+00:00)", repr(response))