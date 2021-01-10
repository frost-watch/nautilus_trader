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

from nautilus_trader.adapters.ccxt.providers cimport CCXTInstrumentProvider
from nautilus_trader.live.execution cimport LiveExecutionClient


cdef class CCXTExecutionClient(LiveExecutionClient):
    cdef object _client
    cdef CCXTInstrumentProvider _instrument_provider
    cdef bint _is_connected

    cdef dict _currencies
    cdef object _update_instruments_task
    cdef object _watch_balances_task

    cdef inline void _on_account_state(self, dict response) except *
