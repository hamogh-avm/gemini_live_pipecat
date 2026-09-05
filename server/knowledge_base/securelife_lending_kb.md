# SecureLife Capital — Lending Knowledge Base

This file is the factual source of truth for the outbound lending agent. The prompt states behaviour; this states fact. All figures are demo values. Any exact rate, fee, EMI, or eligibility number for a specific customer is always confirmed by a specialist — this KB gives ranges and rules only.

Each article opens with `## KB-nn · Title`. The `**Bot rule:**` line closes an article and constrains how the agent may use it.

---

## KB-01 · Products offered

- **Personal Loan** — collateral-free; wedding, medical, travel, education, debt consolidation, emergencies, home renovation. Typical tickets ₹2L–₹15L (up to ~₹40–50L profile-dependent).
- **Two-Wheeler Loan** — asset-backed loan to buy a scooter or motorcycle. Down-payment plus EMIs on the balance; the vehicle is financed. Fast, low-documentation, small ticket.
- **Gold Loan** — loan against gold, gold returned on repayment. Fast disbursal, minimal documents.
- **Housing / Home Loan** — new loan, balance transfer, top-up, renovation/construction.
- **SME / Business Finance** — secured/unsecured business loan, working capital, line of credit. Typical tickets ₹25L–₹2Cr.
- **Machinery Loan** — asset-backed; preserves working capital vs. an outright purchase.
- **Loan Against Property (LAP)** — larger tickets, lower rate than unsecured, longer tenure.
- **Loan Against Securities (LAS)** — against shares/MF/insurance; faster, flexible, but carries margin-maintenance risk if the market falls — always disclose honestly.

**Bot rule:** Never assume the product — let the customer reveal it. Never invent a product or feature not listed here; if asked about something not here, say a specialist will confirm.

---

## KB-02 · Interest rates (indicative ranges only)

- **Personal Loan:** starts around **11% per annum**, rising with profile.
- **Two-Wheeler Loan:** typically around **10-14% per annum** depending on tenure, model, and profile.
- **Home Loan:** starts well below unsecured rates; current rates start much lower than older 9%+ loans, which is what makes a balance transfer worth comparing.
- **Business funding:** can be **under 1% per month** for strong profiles.
- **Gold Loan / LAP / LAS:** secured, so lower than unsecured — exact rate depends on the asset and tenure.

**Bot rule:** State rates only as approximate ranges, always with the basis ("per annum" or "per month" — never a bare "%"). Never state an exact rate for the customer's profile as fact; defer that to the specialist. A running-offer teaser rate is a general advertised offer, not a quote.

---

## KB-03 · EMI, down-payment and tenure

- EMI depends on three things: loan amount, interest rate, and tenure. A longer tenure lowers the monthly EMI but increases total interest paid; a shorter tenure does the opposite.
- On an asset loan (two-wheeler, machinery), a **higher down-payment lowers the financed amount**, which lowers the EMI.
- The agent may give a **rough ballpark EMI range** to keep a price-sensitive customer engaged, clearly flagged as approximate, and must immediately defer the exact figure to the specialist. If an honest ballpark isn't possible, say so and route to the specialist rather than guessing.
- The agent must never state an exact EMI as fact.

**Bot rule:** Explain the levers (amount, rate, tenure, down-payment) plainly. A ballpark range is allowed if flagged approximate; an exact EMI is always the specialist's number. Never quote a precise monthly figure as final.

---

## KB-04 · Processing fees and charges

- A one-time **processing fee**, usually around **1% to a few percent** of the loan amount, applies. Everything is disclosed upfront — nothing appears later.
- **Foreclosure / prepayment:** commonly no charge on floating-rate personal and asset loans, but this varies by product — the specialist confirms the exact terms.
- **Part-prepayment** (paying a chunk off early to reduce EMI or tenure) is usually allowed on most loans — the specialist confirms limits per product.
- The exact fee figure for a specific loan is shown by the specialist before signing.

**Bot rule:** Validate the concern honestly, name the fee, defer the exact figure to the specialist. Never claim "no charges" categorically for prepayment without the product being confirmed.

---

## KB-05 · Documents and eligibility (general)

- **Salaried:** ID proof, address proof, recent salary slips, bank statements. **Self-employed:** ID/address proof, bank statements, business proof, and financials as applicable.
- Two-wheeler and gold loans are the lightest on documentation; home and business loans need more.
- **Do not collect** full PAN/Aadhaar/card numbers or OTPs on the call — the agent only notes what discovery needs, one field at a time.
- A lower credit/CIBIL score does not always mean rejection, especially for salaried profiles — but approval is never promised; the specialist assesses.
- **No income proof / new to credit:** options may still exist (e.g. gold loan, or a co-applicant/guarantor route) — the specialist assesses; don't promise.

**Bot rule:** Give the general document list plainly. Never promise approval or state a specific eligibility amount as fact. Never collect sensitive ID numbers or OTPs.

---

## KB-06 · Disbursal speed

- **Personal loan:** money can be in the account within a couple of days once documentation is complete.
- **Gold loan:** fast, often same-day once documents are ready.
- **Two-wheeler loan:** quick, often processed at or near the dealership.
- **Home / business loans:** longer, as they involve more assessment.

**Bot rule:** State speed as a general expectation, tied to "once documents are complete." Never promise a specific approval or disbursal date the agent doesn't control.

---

## KB-07 · Human transfer / specialist handoff

Route to a specialist when: the customer is time-pressed and wants it done now, a genuine funding emergency exists, or an exact figure (rate, EMI, eligibility, foreclosure amount for a specific loan) is needed.

Before a live transfer, prepare a short spoken brief for the receiving specialist: name, personal/business, what they need, rough amount, key objection raised — so the customer doesn't repeat themselves.

**Bot rule:** Confirm the customer has actually agreed to the transfer before connecting. Explainable things (rate ranges, fees, documents, disbursal speed, product comparisons) the agent handles directly; exact personal figures go to the specialist.

---

## KB-08 · Objection handling library

Acknowledge first, always. Take stacked objections one at a time. Never argue.

- **"How did you get my number / who is this?"** — Answer honestly with the real reason for the call, offer an easy out, don't get defensive.
- **"I'm not looking / just browsing / don't remember."** — No pushback. Soften and widen: "No problem at all. When you looked, was there something specific in mind, or just checking?"
- **"Your rates are high."** — Honest ballpark, reframe to net benefit, defer exact: "starts from around 11% and goes up depending on profile — the real question is whether it lowers what you're paying overall."
- **"Hidden charges / processing fee."** — "Everything's disclosed upfront — interest, and a one-time processing fee usually around 1 to a few percent. Nothing appears later; the specialist shows the exact figure before you sign."
- **"I'll just pay cash."** — Don't argue financing is objectively better: "Reasonable instinct — but paying it all at once can leave you short if another expense hits. Spreading it keeps cash in hand."
- **"Bank rejected me / made me run around."** — Empathize, offer a briefed handoff: "I hear that a lot. Let me have someone call you back — I'll brief them fully first, so you won't repeat a word."
- **"My CIBIL/credit score isn't great."** — "A lower score doesn't always mean no, especially for salaried profiles — but I won't promise approval; the specialist will assess properly."
- **"I don't have time / I'm busy."** — Respect immediately: "Understood — then let's do it once, properly. I can connect you now for two minutes, or set a callback whenever suits."
- **"My own bank already offers me loans."** — "They might — the difference is usually speed and how much they'll extend. No harm in comparing; if ours isn't better, stick with your bank."
- **"Are you a robot / real person?"** — Be honest: "I'm a virtual assistant from SecureLife Capital, calling to help and connect you to the right specialist."
- **"Don't call me again."** — Honour immediately, no pushback: "Understood, I'll make sure of that. Apologies for the disturbance — have a good day." Do not re-open discovery.

**Bot rule:** Never argue. Acknowledge, answer honestly using these frames, and never over-promise or invent figures.

---

## KB-09 · Objection handling — local lenders, moneylenders, financiers

One of the most common pushbacks in the Indian market. Handle it honestly, never by rubbishing the local guy.

- **"The local lender / financier gives me more money."** — "That can happen — a local financier isn't bound by the same checks, so sometimes they'll extend more. The flip side is the effective interest is usually much higher and there's nothing in writing. With a regulated NBFC everything's transparent and on record. No harm comparing the actual cost, not just the amount."
- **"Local sahukar / moneylender gives a better interest rate."** — "Honestly, on paper their monthly number can sound smaller — but once you work it out yearly it's often far higher than a regulated loan, and there's no protection if something goes wrong. Worth comparing the real annual cost side by side."
- **"My local jeweller gives more on gold, on the spot."** — "I understand — but a jeweller is an informal arrangement, unregulated, and the effective interest is usually much higher. A regulated NBFC values your gold per RBI norms, transparently, in front of you, and it's quick too. Safer for the same gold."
- **"The dealer / showroom is arranging finance for me already."** — "That's fine, they usually tie up with one or two financiers. No harm checking our number against theirs — dealer finance isn't always the cheapest, and if ours is better you save on every EMI. If theirs wins, go with it."
- **"A DSA / agent promised me approval and a fixed rate."** — "I'd be a little careful there — nobody can honestly promise approval or lock a rate before your profile is assessed. We won't promise a number blind; the specialist gives you the real figure once your details are checked."
- **"Chit fund / committee is cheaper for me."** — "For some people a chit works — but it depends on your turn and there's counterparty risk if the group defaults. A formal loan is predictable and regulated. Depends what you value more, flexibility or certainty."

**Bot rule:** Never disparage the local lender or call the customer foolish. Reframe on transparency, regulation, and real annual cost versus headline amount. Never claim SecureLife is always cheaper — invite a genuine comparison and defer exact figures to the specialist.

---

## KB-10 · Scenario — Two-wheeler loan

- Financed against the vehicle. Customer pays a **down-payment** and finances the balance over a chosen tenure.
- Larger down-payment → smaller financed amount → lower EMI. Longer tenure → lower EMI but more total interest.
- Light documentation, quick processing, small ticket — often arranged at the dealership.
- Common questions: "Do you finance the full on-road price or just ex-showroom?" — typically a percentage of on-road/ex-showroom is financed, rest is down-payment; specialist confirms the exact percentage. "Is insurance included?" — insurance is usually separate; specialist confirms if it can be bundled.

**Bot rule:** Explain mechanics and levers plainly. Ballpark only if flagged approximate; exact EMI is the specialist's number. Don't state financing percentage as fact — defer to specialist.

---

## KB-11 · Scenario — Personal loan (weddings, medical, travel, consolidation)

- Collateral-free, so rate is higher than a secured loan but no asset is pledged. Flexible end-use.
- **Debt consolidation:** pulling multiple EMIs and a costly credit-card balance into one lower-rate loan — often one EMI instead of several, and cheaper overall if the numbers work. The reframe is net saving, not "take more debt."
- **Medical / emergency:** speed matters — a personal loan or gold loan can move fast; if urgent, a live transfer may be right.
- **Wedding:** tenure flexibility is usually the real concern — a longer tenure keeps the EMI comfortable.

**Bot rule:** Route by end-use but don't over-probe personal reasons. For consolidation, always frame on net saving and defer the exact comparison to a sent estimate or the specialist.

---

## KB-12 · Scenario — Gold loan

- Loan against pledged gold; gold returned on full repayment. Fast, minimal documents, often same-day.
- Amount depends on gold weight/purity and RBI-norm valuation — done transparently, in front of the customer.
- Common uses: short-term liquidity, working capital, festival/seasonal needs, emergencies.
- Common worry: valuation ("you'll undervalue it") — see KB-09.

**Bot rule:** Never quote a loan-against-gold amount before valuation. Explain the process and speed; defer the figure.

---

## KB-13 · Scenario — Home loan (new, balance transfer, top-up)

- **New home loan:** larger ticket, longer tenure, more documentation and assessment, slower to process.
- **Balance transfer:** moving an older, higher-rate loan to a lower rate — the EMI often drops meaningfully, and on a large balance that's real money over years. Only worth it if the net saving clearly beats any transfer cost.
- **Top-up:** an additional amount on top of the transferred loan, at the same low home-loan rate — often used for renovation, cheaper than a personal loan.
- Process is mostly digital now; most of the legwork is handled for the customer.

**Bot rule:** Frame balance transfer purely on net saving. Never quote an exact new EMI — send a savings estimate and/or defer to the specialist.

---

## KB-14 · Scenario — Business / SME, machinery, LAP, LAS

- **Working capital / line of credit / unsecured business loan:** for day-to-day operations, stock, seasonal needs. Rates can be under 1% per month for strong profiles.
- **Machinery loan:** asset-backed; preserves working capital versus paying cash outright — the machine effectively pays for itself over time from added production.
- **LAP (loan against property):** larger tickets, lower rate, longer tenure, no market-linked risk, but slower to process.
- **LAS (loan against securities):** faster and flexible, but carries **margin-maintenance risk** — if the market falls, a top-up may be required. Always disclose this honestly; for multi-year needs, LAP is often steadier.
- Common business objections: "I'll pay from profits" — preserve-working-capital reframe; "seasonal cash flow, rigid EMI is hard" — the repayment structure can be tailored, route to specialist.

**Bot rule:** Route business needs to the business/secured desk. Disclose LAS margin risk honestly whenever LAS comes up. Never quote exact business rates or structures — defer to the specialist.

---

## KB-15 · Quick facts the agent may state directly

- Products: personal, two-wheeler, gold, home, business/SME, machinery, LAP, LAS.
- Personal loan rate starts ~11% p.a.; two-wheeler ~10-14% p.a. (indicative).
- Processing fee: one-time, ~1% to a few percent, disclosed upfront.
- Personal loan disbursal: within a couple of days once documents are complete. Gold: often same-day.
- No PAN/Aadhaar/card/OTP collected on this call.
- All exact figures confirmed by the specialist; approval never promised.

**Bot rule:** These may be stated directly. Anything beyond them that needs a precise personal number is a specialist matter.

---

## KB-16 · Data privacy and conduct

- The agent collects only what discovery needs, one field at a time. No sensitive ID numbers or OTPs.
- The call follows TRAI/RBI norms; opt-out requests are honoured immediately and permanently.
- The agent identifies itself and the purpose of the call clearly at the start, and is honest if asked whether it's a bot.

**Bot rule:** If asked about data or privacy, answer plainly and reassuringly using the above. Escalate anything beyond it to the specialist.
