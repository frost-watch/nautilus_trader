import datetime
from decimal import Decimal
from functools import partial
import json
import os
import pathlib
import sys

import fsspec.implementations.memory
from numpy import dtype
import orjson
import pandas as pd
from pandas import CategoricalDtype
import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from examples.strategies.orderbook_imbalance import OrderbookImbalance
from nautilus_trader.adapters.betfair.common import BETFAIR_VENUE
from nautilus_trader.adapters.betfair.data import on_market_update
from nautilus_trader.adapters.betfair.providers import BetfairInstrumentProvider
from nautilus_trader.adapters.betfair.util import historical_instrument_provider_loader
from nautilus_trader.backtest.data_loader import CSVParser
from nautilus_trader.backtest.data_loader import DataCatalog
from nautilus_trader.backtest.data_loader import DataLoader
from nautilus_trader.backtest.data_loader import ParquetParser
from nautilus_trader.backtest.data_loader import TextParser
from nautilus_trader.backtest.data_loader import is_custom_data
from nautilus_trader.backtest.data_loader import parse_timestamp
from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.common.providers import InstrumentProvider
from nautilus_trader.core.datetime import millis_to_nanos
from nautilus_trader.data.wrangling import QuoteTickDataWrangler
from nautilus_trader.data.wrangling import TradeTickDataWrangler
from nautilus_trader.model import currencies
from nautilus_trader.model.currencies import GBP
from nautilus_trader.model.data.base import Data
from nautilus_trader.model.data.base import GenericData
from nautilus_trader.model.data.tick import QuoteTick
from nautilus_trader.model.data.tick import TradeTick
from nautilus_trader.model.enums import AccountType
from nautilus_trader.model.enums import BookLevel
from nautilus_trader.model.enums import OMSType
from nautilus_trader.model.enums import VenueType
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.identifiers import Symbol
from nautilus_trader.model.identifiers import Venue
from nautilus_trader.model.instruments.betting import BettingInstrument
from nautilus_trader.model.instruments.currency import CurrencySpot
from nautilus_trader.model.objects import Money
from nautilus_trader.model.objects import Price
from nautilus_trader.model.objects import Quantity
from nautilus_trader.model.orderbook.data import OrderBookData
from nautilus_trader.serialization.arrow.core import register_parquet
from tests.test_kit import PACKAGE_ROOT
from tests.test_kit.providers import TestInstrumentProvider
from tests.test_kit.stubs import TestStubs


TEST_DATA_DIR = str(pathlib.Path(PACKAGE_ROOT).joinpath("data"))

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="test path broken on windows")


@pytest.fixture(scope="function")
def data_loader():
    instrument_provider = BetfairInstrumentProvider.from_instruments([])
    parser = TextParser(
        parser=lambda x, state: on_market_update(
            instrument_provider=instrument_provider, update=orjson.loads(x)
        ),
        instrument_provider_update=historical_instrument_provider_loader,
    )
    return DataLoader(
        path=TEST_DATA_DIR,
        parser=parser,
        glob_pattern="1.166564490*",
        instrument_provider=instrument_provider,
    )


@pytest.fixture(scope="function")
def catalog(data_loader):
    catalog = DataCatalog(path="/", fs_protocol="memory")
    try:
        catalog.fs.rm("/", recursive=True)
    except FileNotFoundError:
        pass
    return catalog


@pytest.fixture(scope="function")
def loaded_catalog(catalog, data_loader):
    catalog.import_from_data_loader(data_loader)
    return catalog


def test_is_custom_data():
    assert not is_custom_data(OrderBookData)
    assert not is_custom_data(TradeTick)
    assert is_custom_data(pd.DataFrame)


@pytest.mark.parametrize(
    "glob, num_files",
    [
        ("**.json", 3),
        ("**.txt", 1),
        ("**.parquet", 2),
        ("**.csv", 11),
    ],
)
def test_data_loader_paths(glob, num_files):
    d = DataLoader(path=TEST_DATA_DIR, parser=TextParser(parser=len), glob_pattern=glob)
    assert len(d.path) == num_files


def test_data_loader_stream():
    loader = DataLoader(path=TEST_DATA_DIR, parser=None, glob_pattern="1.166564490.bz2")
    raw = list(loader.stream_bytes())
    assert len(raw) == 6


def test_data_loader_json_betting_parser():
    instrument_provider = BetfairInstrumentProvider.from_instruments([])

    parser = TextParser(
        parser=lambda x, state: on_market_update(
            instrument_provider=instrument_provider, update=orjson.loads(x)
        ),
        instrument_provider_update=historical_instrument_provider_loader,
    )
    loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=parser,
        glob_pattern="**.bz2",
        instrument_provider=instrument_provider,
    )
    assert len(loader.path) == 3

    data = [x for y in loader.run() for x in y]
    assert len(data) == 30829


def test_data_loader_parquet():
    def filename_to_instrument(fn):
        if "btcusd" in fn:
            return TestInstrumentProvider.btcusdt_binance()
        else:
            raise KeyError()

    def parser(data_type, df, filename):
        instrument = filename_to_instrument(fn=filename)
        if data_type == "quote_ticks":
            df = df.set_index("timestamp")[["bid", "ask", "bid_size", "ask_size"]]
            wrangler = QuoteTickDataWrangler(data_quotes=df, instrument=instrument)
        elif data_type == "trade_ticks":
            wrangler = TradeTickDataWrangler(df=df, instrument=instrument)
        else:
            raise TypeError()
        wrangler.pre_process(0)
        return wrangler.build_ticks()

    loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=ParquetParser(
            data_type="quote_ticks",
            parser=parser,
        ),
        glob_pattern="*quote*.parquet",
        instrument_provider=InstrumentProvider(),
    )
    assert len(loader.path) == 1
    values = [x for vals in loader.run() for x in vals if isinstance(x, QuoteTick)]
    assert len(values) == 451


def test_data_loader_csv(catalog):
    def parse_csv_tick(df, instrument_id, state=None):
        for _, r in df.iterrows():
            ts = millis_to_nanos(pd.Timestamp(r["timestamp"]).timestamp())
            tick = QuoteTick(
                instrument_id=instrument_id,
                bid=Price.from_str(str(r["bid"])),
                ask=Price.from_str(str(r["ask"])),
                bid_size=Quantity.from_int(1_000_000),
                ask_size=Quantity.from_int(1_000_000),
                ts_event_ns=ts,
                ts_recv_ns=ts,
            )
            yield tick

    loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=CSVParser(parser=partial(parse_csv_tick, instrument_id=TestStubs.audusd_id())),
        chunk_size=100 ** 2,
        glob_pattern="truefx-usd*.csv",
    )
    assert len(loader.path) == 1
    values = [x for vals in loader.run() for x in vals if isinstance(x, QuoteTick)]
    assert len(values) == 1000

    # Write to parquet
    catalog.import_from_data_loader(loader=loader)
    data = catalog.quote_ticks()
    assert len(data) == 1000


def test_parse_timestamp():
    assert parse_timestamp(1580453644855000064) == 1580453644855000064
    assert parse_timestamp("2020-01-31T06:54:04.855000064+10:00") == 1580417644855000064
    assert parse_timestamp("2020-01-31 06:54:04.855000064") == 1580453644855000064
    assert parse_timestamp("2020-01-31") == 1580428800000000000


def test_data_catalog_from_env():
    os.environ["NAUTILUS_CATALOG"] = "memory:///"
    c = DataCatalog.from_env()
    assert isinstance(c.fs, fsspec.implementations.memory.MemoryFileSystem)
    assert str(c.path) == "/"

    os.environ["NAUTILUS_CATALOG"] = "file:///data"
    c = DataCatalog.from_env()
    assert isinstance(c.fs, fsspec.implementations.local.LocalFileSystem)
    assert str(c.path) == "/data"


def test_data_catalog_instruments_df(loaded_catalog):
    instruments = loaded_catalog.instruments()
    assert len(instruments) == 2


def test_data_catalog_instruments_filtered_df(loaded_catalog):
    instrument_id = (
        "Basketball,,29628709,20191221-001000,ODDS,MATCH_ODDS,1.166564490,237491,.BETFAIR"
    )
    instruments = loaded_catalog.instruments(instrument_ids=[instrument_id])
    assert len(instruments) == 1
    assert instruments["instrument_id"].iloc[0] == instrument_id


def test_data_catalog_instruments_no_partition(loaded_catalog):
    ds = pq.ParquetDataset(
        path_or_paths=str(loaded_catalog.path / "betting_instrument.parquet/"),
        filesystem=loaded_catalog.fs,
    )
    partitions = ds.partitions
    assert not partitions.levels


def test_data_catalog_instruments_as_nautilus(loaded_catalog):
    instruments = loaded_catalog.instruments(as_nautilus=True)
    assert all(isinstance(ins, BettingInstrument) for ins in instruments)


def test_data_catalog_metadata(loaded_catalog):
    assert ds.parquet_dataset(
        f"{loaded_catalog.path}/trade_tick.parquet/_metadata", filesystem=loaded_catalog.fs
    )
    assert ds.parquet_dataset(
        f"{loaded_catalog.path}/trade_tick.parquet/_common_metadata", filesystem=loaded_catalog.fs
    )


def test_data_catalog_dataset_types(loaded_catalog):
    dataset = ds.dataset(
        str(loaded_catalog.path / "trade_tick.parquet"), filesystem=loaded_catalog.fs
    )
    schema = {n: t.__class__.__name__ for n, t in zip(dataset.schema.names, dataset.schema.types)}
    expected = {
        "price": "DataType",
        "size": "DataType",
        "aggressor_side": "DictionaryType",
        "match_id": "DataType",
        "ts_event_ns": "DataType",
        "ts_recv_ns": "DataType",
    }
    assert schema == expected


def test_data_catalog_parquet():
    def filename_to_instrument(fn):
        if "btcusd" in fn:
            return TestInstrumentProvider.btcusdt_binance()
        else:
            raise KeyError()

    def parser(data_type, df, filename):
        instrument = filename_to_instrument(fn=filename)
        df = df.set_index("timestamp")
        if data_type == "quote_ticks":
            df = df[["bid", "ask", "bid_size", "ask_size"]]
            wrangler = QuoteTickDataWrangler(data_quotes=df, instrument=instrument)
        elif data_type == "trade_ticks":
            wrangler = TradeTickDataWrangler(data=df, instrument=instrument)
        else:
            raise TypeError()
        wrangler.pre_process(0)
        return wrangler.build_ticks()

    quote_loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=ParquetParser(
            data_type="quote_ticks",
            parser=parser,
        ),
        glob_pattern="*quote*.parquet",
        instrument_provider=InstrumentProvider(),
    )
    trade_loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=ParquetParser(
            data_type="trade_ticks",
            parser=parser,
        ),
        glob_pattern="*trade*.parquet",
        instrument_provider=InstrumentProvider(),
    )

    # Write to parquet
    catalog = DataCatalog.from_uri("memory:///")
    catalog.import_from_data_loader(loader=quote_loader)
    catalog.import_from_data_loader(loader=trade_loader)
    assert len(catalog.quote_ticks(instrument_ids=["BTC/USDT.BINANCE"])) == 451
    assert len(catalog.trade_ticks(instrument_ids=["BTC/USDT.BINANCE"])) == 2001


def test_partition_key_correctly_remapped(catalog):
    instrument = TestInstrumentProvider.default_fx_ccy("AUD/USD")
    tick = QuoteTick(
        instrument_id=instrument.id,
        bid=Price(10, 1),
        ask=Price(11, 1),
        bid_size=Quantity(10, 1),
        ask_size=Quantity(10, 1),
        ts_recv_ns=0,
        ts_event_ns=0,
    )
    catalog._write_chunks(chunk=[instrument, tick])
    df = catalog.quote_ticks()
    assert len(df) == 1
    # Ensure we "unmap" the keys that we write the partition filenames as;
    # this instrument_id should be AUD/USD not AUD-USD
    assert df.iloc[0]["instrument_id"] == instrument.id.value


def test_data_catalog_filter(loaded_catalog):
    assert len(loaded_catalog.order_book_deltas()) == 2384
    assert (
        len(loaded_catalog.order_book_deltas(filter_expr=ds.field("delta_type") == "DELETE")) == 351
    )


def test_data_catalog_parquet_dtypes(loaded_catalog):
    result = loaded_catalog.trade_ticks().dtypes.to_dict()
    expected = {
        "aggressor_side": CategoricalDtype(categories=["UNKNOWN"], ordered=False),
        "instrument_id": CategoricalDtype(
            categories=[
                "Basketball,,29628709,20191221-001000,ODDS,MATCH_ODDS,1.166564490,237491,.BETFAIR",
                "Basketball,,29628709,20191221-001000,ODDS,MATCH_ODDS,1.166564490,60424,.BETFAIR",
            ],
            ordered=False,
        ),
        "match_id": dtype("O"),
        "price": dtype("float64"),
        "size": dtype("float64"),
        "ts_event_ns": dtype("int64"),
        "ts_recv_ns": dtype("int64"),
    }
    assert result == expected


def test_data_catalog_query_filtered(loaded_catalog):
    ticks = loaded_catalog.trade_ticks()
    assert len(ticks) == 312

    ticks = loaded_catalog.trade_ticks(start="2019-12-20 20:56:18")
    assert len(ticks) == 123

    ticks = loaded_catalog.trade_ticks(start=1576875378384999936)
    assert len(ticks) == 123

    ticks = loaded_catalog.trade_ticks(start=datetime.datetime(2019, 12, 20, 20, 56, 18))
    assert len(ticks) == 123


def _news_event_to_dict(self):
    return {
        "name": self.name,
        "impact": self.impact,
        "currency": self.currency,
        "ts_event_ns": self.ts_event_ns,
    }


def _news_event_from_dict(data):
    return NewsEvent(**data)


class NewsEvent(Data):
    def __init__(self, name, impact, currency, ts_event_ns):
        super().__init__(ts_event_ns=ts_event_ns, ts_recv_ns=ts_event_ns)
        self.name = name
        self.impact = impact
        self.currency = currency


def test_data_loader_generic_data(catalog):
    register_parquet(
        NewsEvent,
        _news_event_to_dict,
        _news_event_from_dict,
        partition_keys=("currency",),
        force=True,
    )

    def make_news_event(df, state=None):
        for _, row in df.iterrows():
            yield NewsEvent(
                name=row["Name"],
                impact=row["Impact"],
                currency=row["Currency"],
                ts_event_ns=millis_to_nanos(pd.Timestamp(row["Start"]).timestamp()),
            )

    loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=CSVParser(parser=make_news_event),
        glob_pattern="news_events.csv",
    )
    catalog.import_from_data_loader(loader=loader)
    df = catalog.generic_data(cls=NewsEvent, filter_expr=ds.field("currency") == "USD")
    assert len(df) == 22925
    data = catalog.generic_data(
        cls=NewsEvent, filter_expr=ds.field("currency") == "USD", as_nautilus=True
    )
    assert len(data) == 22925 and isinstance(data[0], GenericData)


def test_data_catalog_append(catalog):
    instrument_data = json.loads(open(TEST_DATA_DIR + "/crypto_instruments.json").read())

    objects = []
    for data in instrument_data:
        symbol, venue = data["id"].rsplit(".", maxsplit=1)
        instrument = CurrencySpot(
            instrument_id=InstrumentId(symbol=Symbol(symbol), venue=Venue(venue)),
            base_currency=getattr(currencies, data["base_currency"]),
            quote_currency=getattr(currencies, data["quote_currency"]),
            price_precision=data["price_precision"],
            size_precision=data["size_precision"],
            price_increment=Price.from_str(data["price_increment"]),
            size_increment=Quantity.from_str(data["size_increment"]),
            lot_size=data["lot_size"],
            max_quantity=data["max_quantity"],
            min_quantity=data["min_quantity"],
            max_notional=data["max_notional"],
            min_notional=data["min_notional"],
            max_price=data["max_price"],
            min_price=data["min_price"],
            margin_init=Decimal(1.0),
            margin_maint=Decimal(1.0),
            maker_fee=Decimal(1.0),
            taker_fee=Decimal(1.0),
            ts_event_ns=0,
            ts_recv_ns=0,
        )
        objects.append(instrument)
    catalog._write_chunks(chunk=objects[:3])
    catalog._write_chunks(chunk=objects[3:])
    assert len(catalog.instruments()) == 6


def test_catalog_invalid_partition_key(catalog):
    register_parquet(
        NewsEvent,
        _news_event_to_dict,
        _news_event_from_dict,
        partition_keys=("name",),
        force=True,
    )

    def make_news_event(df, state=None):
        for _, row in df.iterrows():
            yield NewsEvent(
                name=row["Name"],
                impact=row["Impact"],
                currency=row["Currency"],
                ts_event_ns=millis_to_nanos(pd.Timestamp(row["Start"]).timestamp()),
            )

    loader = DataLoader(
        path=TEST_DATA_DIR,
        parser=CSVParser(parser=make_news_event),
        glob_pattern="news_events.csv",
    )
    with pytest.raises(ValueError):
        catalog.import_from_data_loader(loader=loader)


def test_data_catalog_backtest_data_no_filter(loaded_catalog):
    data = loaded_catalog.load_backtest_data()
    assert len(sum(data.values(), [])) == 2323


def test_data_catalog_backtest_data_filtered(loaded_catalog):
    instruments = loaded_catalog.instruments(as_nautilus=True)
    engine = BacktestEngine(bypass_logging=True)
    engine = loaded_catalog.setup_engine(
        engine=engine,
        instruments=[instruments[1]],
        start_timestamp=1576869877788000000,
    )
    engine.add_venue(
        venue=BETFAIR_VENUE,
        venue_type=VenueType.EXCHANGE,
        account_type=AccountType.CASH,
        base_currency=GBP,
        oms_type=OMSType.NETTING,
        starting_balances=[Money(10000, GBP)],
        order_book_level=BookLevel.L2,
    )
    engine.run()
    # Total events 1045
    assert engine.iteration == 600


@pytest.mark.skip(reason="flaky")
def test_data_catalog_backtest_run(loaded_catalog):
    instruments = loaded_catalog.instruments(as_nautilus=True)
    engine = BacktestEngine(bypass_logging=True)
    engine = loaded_catalog.setup_engine(engine=engine, instruments=[instruments[1]])
    engine.add_venue(
        venue=BETFAIR_VENUE,
        venue_type=VenueType.EXCHANGE,
        account_type=AccountType.CASH,
        base_currency=GBP,
        oms_type=OMSType.NETTING,
        starting_balances=[Money(10000, GBP)],
        order_book_level=BookLevel.L2,
    )
    strategy = OrderbookImbalance(
        instrument=instruments[1], max_trade_size=Decimal("50"), order_id_tag="OI"
    )
    engine.run(strategies=[strategy])
    positions = engine.trader.generate_positions_report()
    assert positions["realized_points"].astype(float).sum() == -0.00462297183247178
