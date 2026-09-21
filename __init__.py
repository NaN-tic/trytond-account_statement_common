# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from trytond.pool import Pool

from . import account, account_bank, ir, journal, move, statement
from . import statement_aeb43, statement_analytic


def register():
    Pool.register(
        ir.ModelData,
        account.Move,
        account.MoveLine,
        account.Payment,
        journal.JournalWeight,
        journal.Journal,
        statement.Statement,
        statement.Line,
        statement.Origin,
        statement.OriginSuggestedLine,
        statement.AddMultipleInvoicesStart,
        statement.AddMultipleMoveLinesStart,
        statement.LinkInvoiceStart,
        statement.OriginCreateStamentLineStart,
        module='account_statement_common', type_='model')
    Pool.register(
        statement.AddMultipleInvoices,
        statement.AddMultipleMoveLines,
        statement.LinkInvoice,
        statement.OriginCreateStamentLine,
        module='account_statement_common', type_='wizard')
    Pool.register(
        statement_aeb43.ImportStatement,
        depends=['account_statement_aeb43'],
        module='account_statement_common', type_='wizard')
    Pool.register(
        account_bank.CompensationMove,
        depends=['account_bank'],
        module='account_statement_common', type_='wizard')
    Pool.register(
        statement_analytic.Line,
        statement_analytic.Origin,
        statement_analytic.OriginSuggestedLine,
        statement_analytic.AnalyticAccountEntry,
        statement_analytic.AnalyticAccountOriginCreateStamentLineStart,
        depends=['analytic_account'],
        module='account_statement_common', type_='model')
    Pool.register(
        move.Move,
        depends=['account_es'],
        module='account_statement_common', type_='model')
