"""Mzdy a daň: záloha podle § 38h, srážková daň, slevy, zvýhodnění na děti a bonus."""

from django.test import SimpleTestCase, TestCase

from core.models import TaxDeclaration, TaxDeclarationChild
from core.money import format_amount
from core.services.insurance import insurance_contributions
from core.services.tax import MonthlyCredits, advance_tax, monthly_credits, withholding_tax
from core.views.payroll_views import calculate_czech_payroll_2026 as calc

from .helpers import make_employee

BASIC = MonthlyCredits(has_declaration=True, basic=2570)
TWO_KIDS = MonthlyCredits(has_declaration=True, basic=2570, children=1267 + 1860)


class AdvanceTaxTests(SimpleTestCase):
    def test_rounding_rules(self):
        self.assertEqual(advance_tax(32000), 4800)
        self.assertEqual(advance_tax(32050), 4815)   # základ 32 100
        self.assertEqual(advance_tax(99.4), 15)      # do 100 Kč na koruny
        self.assertEqual(advance_tax(200000), 34248)  # 23 % nad 146 901 Kč
        self.assertEqual(withholding_tax(10000.9), 1500)


class InsuranceTests(SimpleTestCase):
    def test_statutory_rounding(self):
        # Zdravotní: 13,5 % nahoru, zaměstnanec třetina nahoru, zbytek zaměstnavatel
        self.assertEqual(insurance_contributions(46520), (3303, 2094, 11537, 4187))
        self.assertEqual(insurance_contributions(32000), (2272, 1440, 7936, 2880))
        self.assertEqual(insurance_contributions(25001), (1776, 1126, 6201, 2250))
        self.assertEqual(insurance_contributions(0), (0, 0, 0, 0))


class PayrollCalculationTests(SimpleTestCase):
    def test_without_declaration(self):
        result = calc(32000, 'HPP')
        self.assertEqual(result['emp_tax'], 4800)
        self.assertEqual(result['net'], 32000 - 2272 - 1440 - 4800)

    def test_basic_credit(self):
        result = calc(32000, 'HPP', credits=BASIC)
        self.assertEqual((result['emp_tax'], result['credit_personal']), (2230, 2570))

    def test_children_and_bonus(self):
        result = calc(32000, 'HPP', credits=TWO_KIDS)
        self.assertEqual((result['emp_tax'], result['credit_children'], result['tax_bonus']), (0, 2230, 897))
        self.assertEqual(result['net'], 32000 - 2272 - 1440 + 897)

    def test_bonus_needs_half_minimum_wage_and_50_kc(self):
        self.assertEqual(calc(10000, 'DPP', credits=TWO_KIDS)['tax_bonus'], 0)
        one_kid = MonthlyCredits(has_declaration=True, basic=2570, children=1267)
        self.assertEqual(calc(25300, 'HPP', credits=one_kid)['tax_bonus'], 0)   # vyšlo by 42 Kč
        self.assertEqual(calc(25200, 'HPP', credits=one_kid)['tax_bonus'], 57)

    def test_withholding_tax_for_small_dpp_without_declaration(self):
        result = calc(10000, 'DPP')
        self.assertTrue(result['withholding'])
        self.assertEqual((result['emp_tax'], result['net']), (1500, 8500))
        self.assertEqual(calc(10000, 'DPP', credits=BASIC)['net'], 10000)

    def test_deductions_keep_haler(self):
        result = calc(42480, 'HPP')
        self.assertEqual(result['emp_deductions'], round(result['emp_sp'] + result['emp_zp'] + result['emp_tax'], 2))


class DeclarationEffectTests(TestCase):
    def test_credits_from_signed_month_until_withdrawal(self):
        employee = make_employee('jan')
        declaration = TaxDeclaration.objects.create(employee=employee, year=2026, signed_on='2026-03-10')
        TaxDeclarationChild.objects.create(declaration=declaration, first_name='A', last_name='B',
                                           birth_number='1652154445', claim='2', ztpp=True)
        self.assertFalse(monthly_credits(employee, 2026, 2).has_declaration)
        credits = monthly_credits(employee, 2026, 3)
        self.assertEqual((credits.basic, credits.children), (2570, 3720))  # 2. dítě se ZTP/P dvojnásobek
        declaration.withdrawn_on = '2026-04-15'
        declaration.save()
        self.assertTrue(monthly_credits(employee, 2026, 4).has_declaration)
        self.assertFalse(monthly_credits(employee, 2026, 5).has_declaration)


class MoneyFormatTests(SimpleTestCase):
    def test_format(self):
        self.assertEqual(format_amount(1234567.005), '1\xa0234\xa0567,01')
        self.assertEqual(format_amount(2.675), '2,68')
        self.assertEqual(format_amount(-25000), '-25\xa0000,00')
        self.assertEqual(format_amount('abc'), 'abc')
        self.assertEqual(format_amount(1234.5, separator=' '), '1 234,50')
