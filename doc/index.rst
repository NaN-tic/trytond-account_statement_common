Account Statement Common
########################

This module provides shared statement management and reconciliation. It can be
activated without a bank synchronization connector. ``account_statement_enable_banking``
depends on this module and supplies the Enable Banking API integration.
``account_statement_bankinplay`` supplies the BankInPlay adviser integration.
The journal's ``statement_provider`` selector is extended by each connector.
Connectors must restrict both scheduled and manual downloads to their selected
provider. Imported identities remain associated with their original provider.

Connector integration
=====================

Extend ``account.statement.journal`` using ``PoolMeta``. Authentication, account
selection, HTTP requests, date policies and pagination belong to the connector.
Within one Tryton transaction:

1. Call ``journal.create_import_statement(date_from, date_to)`` to lock the journal
   and create a registered statement. Both arguments are ``datetime.date`` values.
2. Normalize each page and call
   ``journal.import_statement_transactions(statement, transactions)``. It returns
   the newly saved origins and skips references already imported into that journal
   or repeated within the page.
3. Collect the returned origins from every page and call
   ``journal.finish_import_statement(statement, origins)`` exactly once after the
   download finishes. This sets the closing balance, numbers origins and queues
   suggestions when enabled. Empty statements are validated and posted.

Normalized transactions are dictionaries with these keys:

* ``entry_reference``: stable, nonempty bank transaction identifier within the
  journal. Missing references are skipped. A connector switching providers must
  account for differences in their identifiers before importing overlapping dates.
* ``date``: ``datetime.date`` selected according to the connector's date policy.
* ``amount``: signed ``Decimal`` in the journal's currency. The connector must
  validate the source currency; debits are negative.
* ``description``: optional text.
* ``balance``: optional ``Decimal`` balance after the transaction.
* ``information``: optional dictionary of bank metadata. Use
  ``remittance_information`` for payment descriptions and ISO date strings for
  ``value_date``, ``booking_date`` and ``transaction_date``. The shared suggestion
  engine consumes these canonical keys. Legacy ``eb_*`` XML identifiers are kept
  for the metadata definitions to preserve existing records.

Suggestion matching uses ``information['remittance_information']`` first and
falls back to the origin's ``description`` when that value is missing, null or
contains only spaces. Historical matching and remittance searches use the same
fallback, including for AEB43 imports. Structured metadata remains available
for matching counterparties, references and dates.

Invoice reference suggestions match posted customer invoice numbers or supplier
invoice references, ignoring case, spaces, slashes, dots and hyphens. References
must not be part of a longer number. The company, currency and signed outstanding
amount must match the origin; no prior party-name match is required. This search
does not handle origins with a second currency or payments covering multiple
invoices. Its base weight is configured with ``type-invoice``. Exact normalized
references also receive the full number-match weight for invoices and sales.

Payment suggestions link a payment group only when they contain every payment
in that group, with more than one payment and no failed payments or reconciled
source lines. Single payments and partial groups prefer the posted invoice
associated with an eligible unreconciled source line, then the source line,
and otherwise the individual payment. Partial groups are presented as a parent
suggestion with individual children, not as a link to the full payment group.
Repeated payments from overlapping group/date searches are counted only once.

Connectors can extend ``account.statement.origin.on_change_with_synchronized``
to protect imported origins from editing. The default is false; Enable Banking
preserves its existing rule based on the journal's session.

Possible duplicate movements
============================

Origins with the same journal, company, currency, date, signed amount,
description and information are shown in the ``Possible Duplicates`` tab.
Cancelled origins are excluded. Detection does not require an external
identifier, and never suppresses imports or suggestion searches. Before posting
an origin or a statement, users must confirm the warning or mark the origin's
duplicates as reviewed. Review flags are not copied to new origins.

Connectors can specialize these methods on ``account.statement.origin``:

* ``_get_possible_duplicate_domain(origins)`` selects candidates for a batch.
* ``_get_possible_duplicate_key()`` groups candidates by stable attributes.
* ``_is_possible_duplicate(candidate)`` compares origins sharing that key;
  the default compares their information dictionaries and excludes the origin
  itself. Override it with ``super()`` to add connector-specific criteria.

When relaxing date or amount matching, adapt both the domain and grouping key
so the candidates reach the comparison step. Keep the journal, company and
currency boundaries. Scope connector overrides to their own provider.
Enable Banking requires nonempty, different entry references in its comparison
override. It does not currently parse dates embedded in those references.
Its import-time check for already downloaded references remains separate.

Upgrade both modules together when moving this feature from Enable Banking.
The existing ownership migration transfers its fields, views, message and
translations to the common module, preserving IDs and saved review flags.

Configuration
=============

The ``[account_statement_common]`` configuration section accepts ``queue_name``
and ``party_similarity_threshold``. For compatibility, absent settings fall back
to the previous ``[enable_banking]`` values, then to their existing defaults.
The Enable Banking download queue continues to use ``[enable_banking] queue_name``.

Candidate ranking and application
---------------------------------

Suggestions are ordered by evidence first: exact reference, matching counterparty
(at least 50% similarity), historical pattern, then amount-only matches. The
``Matching Evidence`` column shows this classification. Weights rank candidates
within each evidence level, so a high balance-allocation weight cannot displace
an exact-reference candidate. Grouped suggestions use their weakest child's
evidence level.

Combinations only use amounts with the origin's sign and group entries by party
(or by account when there is no party). They do not mix unrelated counterparties
or offset debits against credits to obtain the target amount. Origins with a
second currency are excluded from this combination search. The defaults are:

* ``move-line-max-count``: 5 lines per combination.
* ``combination-all-max-count``: 3 lines for general combinations.
* ``combination-line-penalty``: 5 points for each additional line.
* ``combination-party-penalty``: 20 points for each additional party in grouped
  proposals, including those produced by other candidate sources.
* ``date-match``: 20; ``party-match``: 40; ``number-match``: 80.
* ``type-combination-all``: 40.

Configured journal weights override these defaults. Candidate enumeration keeps
the existing computation budget and a cap of 100 matches per search pass, but
does not stop because another candidate already has a high weight. Historical
patterns use posted origins in the same company and journal, with the same sign
and second currency, within ``origin-delta-days`` of the transaction date and
not after it. Only patterns without linked documents are copied as account
allocations; their split amounts remain for manual completion.

``Apply Suggestions Automatically`` is disabled by default. Searching still
creates the candidate list. When enabled, the separate application step requires
an exact-reference candidate, the ``origin-similarity`` minimum weight, and a
weight advantage greater than ``auto-use-margin`` (default 20) over the next
exact-reference alternative. The proposal and its children must total the pending
amount, without a second currency. Otherwise, apply a suggestion manually with
``Use``. Ambiguity is checked before trimming the candidate list.

Upgrade the module before using these changes, to install the journal option,
stored evidence level and updated views. Existing suggestions retain their old
scores until recalculated; regenerate suggestions on pending origins to obtain
the new candidate selection and ranking.

Upgrading an existing Enable Banking installation
================================================

Deploy both modules together, plus the updated ``account_mx`` and ``aeat_303``
modules when installed. Refresh the module list, mark
``account_statement_common`` for activation and mark
``account_statement_enable_banking`` and the affected installed modules for
upgrade. Apply those changes together: the dependency order loads the common
module first. For command-line upgrades, use ``--activate-dependencies``.

Before loading the common XML, the registration migration transfers ownership of
shared XML records, models, fields, views and translations from the connector.
It preserves record IDs and model/table names, including statement origins,
suggestions, weights, sequences and journal links. Sessions, credentials and
Enable Banking's scheduled synchronization method remain with the connector.
The migration is idempotent. Custom modules referencing moved XML identifiers
must replace the ``account_statement_enable_banking`` prefix with
``account_statement_common``.

The ``nantic`` module continues to depend on Enable Banking. ``account_mx`` and
``aeat_303`` extend the common module independently of the selected gateway.
