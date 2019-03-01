#!/usr/bin/env python3
# -------------------------------------------------------------------------------------------------
# <copyright file="test_serialization.py" company="Invariance Pte">
#  Copyright (C) 2018-2019 Invariance Pte. All rights reserved.
#  The use of this source code is governed by the license as found in the LICENSE.md file.
#  http://www.invariance.com
# </copyright>
# -------------------------------------------------------------------------------------------------

import unittest

from inv_trader.model.objects import *
from inv_trader.portfolio.sizing import FixedRiskSizer
from test_kit.stubs import TestStubs


class FixedRiskSizerTests(unittest.TestCase):

    def setUp(self):
        # Fixture Setup
        self.sizer = FixedRiskSizer(TestStubs.instrument_gbpusd())

    def test_can_calculate_single_unit_size(self):
        # Arrange
        equity = Money(1000000)

        # Act
        result = self.sizer.calculate(
            equity,
            1,
            Price('1.00100'),
            Price('1.00000'),
            leverage=50,
            unit_batch_size=1000)

        # Assert
        self.assertEqual(Quantity(9992000), result)

    def test_can_calculate_single_unit_size_when_risk_too_high(self):
        # Arrange
        equity = Money(100000)

        # Act
        result = self.sizer.calculate(
            equity,
            1,
            Price('3.00000'),
            Price('1.00000'),
            leverage=50,
            unit_batch_size=1000)

        # Assert
        self.assertEqual(Quantity(0), result)

    def test_can_impose_hard_limit(self):
        # Arrange
        equity = Money(1000000)

        # Act
        result = self.sizer.calculate(
            equity,
            1,
            Price('1.00100'),
            Price('1.00000'),
            leverage=50,
            hard_limit=500000,
            units=1,
            unit_batch_size=1000)

        # Assert
        self.assertEqual(Quantity(500000), result)

    def test_can_calculate_multiple_unit_size(self):
        # Arrange
        equity = Money(1000000)

        # Act
        result = self.sizer.calculate(
            equity,
            1,
            Price('1.00100'),
            Price('1.00000'),
            leverage=50,
            units=3,
            unit_batch_size=1000)

        # Assert
        self.assertEqual(Quantity(3331000), result)

    def test_can_calculate_multiple_unit_size_larger_batches(self):
        # Arrange
        equity = Money(1000000)

        # Act
        result = self.sizer.calculate(
            equity,
            1,
            Price('1.00087'),
            Price('1.00000'),
            units=4,
            unit_batch_size=25000)

        # Assert
        self.assertEqual(Quantity(2875000), result)