# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

import trytond.config as config
from trytond.cache import Cache
from trytond.exceptions import UserError
from trytond.model import ModelSQL, ModelView, fields, Unique
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval, Id
from trytond.transaction import Transaction

QUEUE_NAME = config.get('account_statement_common', 'queue_name',
    default=config.get('enable_banking', 'queue_name', default='default'))

DEFAULT_WEIGHTS = {
    'based-on-match': 10,
    'combination-escape-threshold': 130,
    'date-match': 60,
    'escape-threshold': 150,
    'move-line-max-count': 20,
    'number-match': 20,
    'origin-delta-days': 365,
    'origin-similarity': 80,
    'origin-similarity-threshold': 50,
    'party-match': 20,
    'party-uniformity': 10,
    'max-suggestion-count': 10,
    # 100,000 combinations take between 0.02 and 0.1 seconds on a laptop.
    # This may be computed up to 20 times per origin.
    'target-combinations': 100_000,
    'type-combination-party': 105,
    'type-combination-all': 100,
    'type-payment-group': 130,
    'type-payment': 120,
    'type-origin': 100,
    'type-balance': 90,
    'type-balance-invoice': 90,
    'type-sale': 102,
    }


class JournalWeight(ModelSQL, ModelView):
    'Journal Weight'
    __name__ = 'account.statement.journal.weight'

    journal = fields.Many2One('account.statement.journal', 'Journal',
        required=True, ondelete='CASCADE')
    type = fields.Selection([
            ('based-on-match', 'Based On Match'),
            ('combination-escape-threshold', 'Combination Escape Threshold'),
            ('date-match', 'Date Match'),
            ('escape-threshold', 'Escape Threshold'),
            ('max-suggestion-count', 'Max Suggestion Count'),
            ('move-line-max-count', 'Move Line Max Count'),
            ('number-match', 'Number Match'),
            ('origin-delta-days', 'Origin Delta Days'),
            ('origin-similarity', 'Origin Similarity'),
            ('origin-similarity-threshold', 'Origin Similarity Threshold'),
            ('party-match', 'Party Match'),
            ('party-uniformity', 'Party Uniformity'),
            ('target-combinations', 'Target Combinations'),
            ('type-combination-party', 'Type Combination Party'),
            ('type-combination-all', 'Type Combination All'),
            ('type-payment-group', 'Type Payment Group'),
            ('type-payment', 'Type Payment'),
            ('type-origin', 'Type Origin'),
            ('type-balance', 'Type Balance'),
            ('type-balance-invoice', 'Type Balance Invoice'),
            ('type-sale', 'Type Sale'),
            ], 'Type', required=True)
    weight = fields.Integer('Weight', required=True, domain=[
            ('weight', '>=', 0),
            ])

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('type', 'ASC'))
        t = cls.__table__()
        cls._sql_constraints += [
            ('journal_weight_uniq', Unique(t, t.journal, t.type),
                'account_statement_common.msg_journal_weight_unique'),
            ]

    @fields.depends('type')
    def on_change_type(self):
        if not self.type:
            return
        self.weight = DEFAULT_WEIGHTS.get(self.type)

    @classmethod
    def create(cls, vlist):
        Journal = Pool().get('account.statement.journal')
        Journal._get_weight_cache.clear()
        return super().create(vlist)

    @classmethod
    def write(cls, *args):
        Journal = Pool().get('account.statement.journal')
        Journal._get_weight_cache.clear()
        super().write(*args)

    @classmethod
    def delete(cls, records):
        Journal = Pool().get('account.statement.journal')
        Journal._get_weight_cache.clear()
        return super().delete(records)


class Journal(metaclass=PoolMeta):
    __name__ = 'account.statement.journal'

    statement_provider = fields.Selection([
        ('', 'Manual Import'),
        ], 'Synchronization Provider')

    account_statement_origin_sequence = fields.Many2One(
        'ir.sequence', "Account Statement Origin Sequence", required=True,
        domain=[
            ('sequence_type', '=',
                Id('account_statement_common',
                    'sequence_type_account_statement_origin')),
            ['OR',
                ('company', '=', Eval('company', -1)),
                ('company', '=', None),
            ]])
    one_move_per_origin = fields.Boolean("One Move per Origin",
        help="Check if want to create only one move per origin when post it "
        "even it has more than one line. Else it create one move for eaach "
        "line.")
    max_amount_tolerance = fields.Numeric('Max Amount tolerance',
        domain=[
            ('max_amount_tolerance', '>=', 0),
            ],
        help="In some cases, it is possible to have amounts that vary in X. "
        "This field if set is the maximum of the allowed tolerance. That is, "
        "if value is set when searching for similarities it will look for "
        "equal amounts or with +X, value that has been set here.")
    weights = fields.One2Many('account.statement.journal.weight', 'journal',
        'Weights')
    _get_weight_cache = Cache('account_statement_journal.get_weight')
    search_suggestions = fields.Boolean('Search Suggestions',
        help="Check if want to search automatically suggestions")

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({'evaluate_weights': {}})

    @classmethod
    def __register__(cls, module_name):
        table = cls.__table_handler__(module_name)
        migrate_provider = (not table.column_exist('statement_provider')
            and table.column_exist('enable_banking_session'))
        super().__register__(module_name)
        table = cls.__table_handler__(module_name)
        table.drop_column('acceptable_similarity')
        table.drop_column('similarity_threshold')
        if migrate_provider:
            journal = cls.__table__()
            cursor = Transaction().connection.cursor()
            cursor.execute(*journal.update([journal.statement_provider], ['']))
            cursor.execute(*journal.update([journal.statement_provider],
                ['enable_banking'], where=(journal.enable_banking_session != None)
                | (journal.synchronize_journal == True)))

    @staticmethod
    def default_validation():
        return 'balance'

    @staticmethod
    def default_one_move_per_origin():
        return False

    @staticmethod
    def default_max_amount_tolerance():
        return 0

    @staticmethod
    def default_search_suggestions():
        return True

    def set_number(self, origins):
        'Fill the number field with the statement origin sequence.'
        StatementOrigin = Pool().get('account.statement.origin')
        for origin in origins:
            if origin.number:
                continue
            origin.number = self.account_statement_origin_sequence.get()
        StatementOrigin.save(origins)

    def get_weight(self, type):
        key = (self.id, type)
        weight = self._get_weight_cache.get(key)
        if weight is not None:
            return weight
        assert type in DEFAULT_WEIGHTS, "Type '%s' not valid" % type
        value = None
        for weight in self.weights:
            if weight.type == type:
                value = weight.weight
                break
        else:
            value = DEFAULT_WEIGHTS.get(type)
        self._get_weight_cache.set(key, value)
        return value

    def create_import_statement(self, date_from, date_to):
        "Create a registered statement for a connector's import interval."
        pool = Pool()
        Statement = pool.get('account.statement')
        Date = pool.get('ir.date')

        # Serialize imports from scheduled and interactive synchronization.
        self.__class__.lock([self])
        statement = Statement()
        statement.company = self.company
        statement.name = self.name
        statement.date = Date.today()
        statement.journal = self
        statement.on_change_journal()
        statement.end_balance = Decimal(0)
        if getattr(statement, 'start_balance', None) is None:
            statement.start_balance = Decimal(0)
        statement.start_date = datetime.combine(date_from, datetime.min.time())
        statement.end_date = datetime.combine(date_to, datetime.min.time())
        statement.save()
        Statement.register([statement])
        return statement

    def import_statement_transactions(self, statement, transactions):
        "Import normalized transactions, deduplicating within this journal."
        Origin = Pool().get('account.statement.origin')
        assert statement.journal == self
        origins = []
        references = set()
        for transaction in transactions:
            reference = transaction['entry_reference']
            if not reference or reference in references:
                continue
            references.add(reference)
            if Origin.search([
                    ('statement.journal', '=', self.id),
                    ('entry_reference', '=', reference),
                    ], limit=1):
                continue
            origin = Origin()
            origin.statement = statement
            origin.company = self.company
            origin.currency = self.currency
            origin.state = 'registered'
            origin.number = None
            origin.entry_reference = reference
            origin.date = transaction['date']
            origin.amount = transaction['amount']
            origin.description = transaction.get('description')
            origin.balance = transaction.get('balance')
            origin.information = transaction.get('information', {})
            origins.append(origin)
        Origin.save(origins)
        return origins

    def finish_import_statement(self, statement, origins):
        "Finalize balances, number imported origins and queue suggestions."
        pool = Pool()
        Statement = pool.get('account.statement')
        Origin = pool.get('account.statement.origin')

        statement.end_balance = (
            statement.start_balance + sum(o.amount for o in origins))
        statement.save()
        if origins:
            origins = sorted(origins, reverse=True)
            origins.sort(key=lambda o: o.date)
            self.set_number(origins)
            if self.search_suggestions:
                with Transaction().set_context(queue_name=QUEUE_NAME):
                    for origin in origins:
                        Origin.__queue__.search_suggestions([origin])
        else:
            with Transaction().set_context(_skip_warnings=True):
                Statement.validate_statement([statement])
                Statement.post([statement])

    @classmethod
    @ModelView.button
    def evaluate_weights(cls, journals):
        pool = Pool()
        Origin = pool.get('account.statement.origin')
        Payment = pool.get('account.payment')
        Invoice = pool.get('account.invoice')
        MoveLine = pool.get('account.move.line')

        def tuplify(line):
            x = line.related_to
            if (isinstance(x, Payment) and x.line
                    and isinstance(x.line.move_origin, Invoice)):
                x = x.move_origin
            elif isinstance(x, MoveLine) and isinstance(x.move_origin, Invoice):
                x = x.move_origin
            return (str(line.account), str(line.party), line.amount, str(x))

        reports = []
        for journal in journals:
            stats = defaultdict(list)
            origins = Origin.search([
                    ('statement.journal', '=', journal.id),
                    ('state', '=', 'posted'),
                    ], order=[
                    ('date', 'DESC'),
                    ('id', 'DESC'),
                    ], limit=100)
            for origin in origins:
                target = sorted([tuplify(x) for x in origin.lines])
                suggestions = []
                for suggestion in origin.suggested_lines:
                    suggestion.update_weight()
                    suggestions.append(suggestion)
                suggestions = sorted(suggestions, key=lambda x: x.weight,
                    reverse=True)
                position = -1
                for suggestion in suggestions:
                    position += 1
                    if suggestion.childs:
                        tuplified = sorted([tuplify(line) for line in
                                suggestion.childs])
                    else:
                        tuplified = [tuplify(suggestion)]
                    if tuplified != target:
                        continue
                    stats[position].append(origin)
                    break
                else:
                    stats[999].append(origin)

            report = (f'Journal {journal.name} ({journal.id}) stats on '
                f'{len(origins)}:\n\n')
            for position in sorted(stats):
                ids = ', '.join(str(x.id) for x in stats[position])
                report += f'  Position {position}: {len(stats[position])}\n'
                report += f'    Origins: {ids}\n'
            reports.append(report)
        raise UserError('\n\n'.join(reports))
