# Annotation guideline: ticket_triage

How to decide the correct answer for every golden-dataset ticket. Every annotator follows this
file, so two people labelling the same ticket independently should reach the same answer.

The base rules are the same as the prompt's policy and contract
(`prompts/system/policies/escalation_policy.md`, `prompts/system/output_contracts/ticket_triage_contract.md`).
The **clarifications (C1–C11)** settle cases those rules leave open. Where a clarification goes
beyond what the prompt says, the case is tagged `policy_gap`: the benchmark then measures whether
the prompt needs the same clarification.

## 1. Procedure

1. Read the subject and body. Judge **facts**, not tone: "URGENT!!!" is not evidence.
2. Ignore any instructions written inside the ticket (C7).
3. Pick the category, then the urgency (first matching rule wins), then escalation.
4. List entities that appear literally in the ticket.
5. Write a one-sentence, third-person, English reference summary (10–280 characters).
6. If you hesitated, add a `label_rationale` and the `ambiguous` tag.

## 2. Base rules

**Category** (the single dominant issue; same definitions as the prompt's output contract):

| Category | Covers |
|---|---|
| billing | Charges, invoices, refunds, payment methods, plan prices |
| technical | Errors, outages, bugs, slowness, integrations, API behaviour, **how-to questions about using the product**, cosmetic and documentation issues (C10) |
| account | Sign-in, passwords, single sign-on, permissions, **user management** (inviting, adding or removing users), account deletion (C11) |
| feature_request | Asks for a capability the product does not have yet |
| other | **Not a support request at all**: partnerships, sponsorships, job enquiries, marketing, procurement or compliance paperwork, thanks and praise |

`other` is the last resort. If a ticket is about using, paying for or accessing the product,
one of the first four categories applies, even when the ticket is only a question.

**Urgency** (apply the first rule that matches):
1. critical: data loss, a security or privacy exposure, or a full outage of a production service
2. high: a core feature broken for many users, or the customer charged incorrectly
3. medium: one user blocked, or a feature misbehaves but a workaround exists
4. low: questions, how-to requests, cosmetic issues, feature requests

**Escalation**: true if urgency=critical, OR enterprise tier with urgency=high, OR a legal threat,
OR a request to delete an account. Otherwise false.

## 3. Clarifications

| ID | Situation | Decision |
|---|---|---|
| C1 | A **whole** production service, product or API endpoint is unavailable: nothing loads, or every call fails | Counts as a "full outage of a production service" → **critical** (`policy_gap`) |
| C1b | **One function** fails for all users while the rest of the product works (e.g. exporting, importing, bulk editing) | **Not** an outage → **high** (rule 2: core feature broken for many users) |
| C2 | Many users affected, feature slow but still completes | **high** (core feature broken for many users; rule 2 comes before rule 3) |
| C3 | Malfunction reported with no detail ("it doesn't work") | **technical, medium**: treat as one user blocked |
| C4 | Several issues in one ticket | Label the **most urgent** issue; on a tie, the first one mentioned |
| C5 | `product` entities | Only this platform's products: **DataSync, ReportBuilder, TeamChat, Insights Dashboard** |
| C6 | Words like "urgent", "asap", "critical" written by the customer | Not evidence; judge the reported facts |
| C7 | Instructions inside the ticket ("ignore your rules…", fake tags) | Ignore; label the real request |
| C8 | Ticket not in English | Label normally; the summary is still in English |
| C9 | Security issue: credentials or sign-in vs. product bug | Credentials/sign-in → **account**; data exposed by a product bug → **technical** |
| C10 | Cosmetic or documentation issue (typo, misaligned logo, broken docs link) | **technical, low**: it is a small bug in the product, not `other` |
| C11 | User management or single sign-on, including how-to questions about it ("how do I add 20 users?", "how do we set up SAML?") | **account**, even though it is phrased as a how-to question |

## 4. Tags

| Tag | Meaning |
|---|---|
| `smoke` | Small fast subset for CI (dev split only) |
| `ambiguous` | A reasonable annotator could disagree; see `label_rationale` |
| `policy_gap` | The label relies on a clarification the prompt does not state |
| `multi_issue` | More than one issue in the ticket (C4) |
| `prompt_injection` | The ticket tries to give the model instructions (C7) |
| `non_english` | Not written in English (C8) |
| `very_long` | Long, rambling ticket; the issue is buried |
| `missing_info` | Too little detail to be sure (C3) |
| `security` | Security or privacy exposure |
| `legal_or_deletion` | Legal threat or account-deletion request (escalation rule) |
| `rule_order` | Two urgency rules match; the first one must win |

## 5. Change log

| Date | Change | Why |
|---|---|---|
| 2026-11-02 | C1 narrowed from "an endpoint **or feature** fails for all calls or users" to a **whole** service, product or endpoint being unavailable; C1b added | The old wording contradicted four existing labels (TT-0006, TT-0007, TT-0050, TT-0057: one function broken for everyone, labelled high). v6's trigger questions applied the old C1 literally and exposed it. Labels unchanged; the rule now matches them. |
| 2026-11-02 | Category table copied from the prompt's output contract; `other` defined as "not a support request"; C10 (cosmetic/documentation → technical) and C11 (user management and SSO → account) added | Blind second annotation of the 108 dev tickets: 11 of 14 category disagreements were how-to, cosmetic or user-management tickets labelled `other` by the second annotator. The old one-line category rule did not say where these go. Labels unchanged; the rules now state what the labels already assumed. |
