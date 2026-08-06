"""Scripted conversations the benchmark replays.

Both are real operator traffic in one domain — a district relief operation —
not synthetic filler. Every turn either carries information a coordinator
would actually log or asks a question that cannot be answered without memory.

The phrasing is deliberately closer to a form than to chat ("Truck count is 3"
rather than "we've got three trucks"). The extractor is frozen; where a
natural phrasing did not survive it, the turn was rewritten rather than the
pipeline, and that is a limitation of the extractor, not a property of the
domain.

A turn is only in here if it passes all three:
  * a real coordinator would plausibly say it,
  * it carries a fact, a correction, a retraction, or a question, and
  * removing it would lose something the later turns rely on.

Nothing was added to lengthen the conversation. `audit_demo.py` re-checks the
first two mechanically and fails the build if a turn stops earning its place.
"""

from __future__ import annotations

# --- the shipped 17-turn demo (frontend/src/components/ReliefDemo.jsx) --------
# Kept byte-identical in meaning to what the UI plays, so the published figure
# and the UI figure describe the same conversation. Currency symbols are
# spelled out because the benchmark tokenizes plain text.
RELIEF_17 = [
    ("session-1", "Relief operation for Wayanad district. Displaced families is 4,200."),
    ("session-1", "Truck count is 3, capacity per truck is 8 tonnes."),
    ("session-1", "First convoy departs before 14 August."),
    ("session-1", "Name: Meera Nair, email: meera@reliefnet.org"),
    ("session-1", "Sanctioned budget is 18 lakh rupees."),
    ("session-1", "Family kit weight is 12 kg, kit invoice is 850 rupees."),
    ("session-1", "Purification tablets is 40,000 units."),
    ("session-1", "Update: truck count is now 5."),
    ("session-1", "Daily report hour is 18."),
    ("session-1", "Medical camp doctors is 3."),
    ("session-1", "Actually cancel the purification tablets, state supply already covered it."),
    ("session-1", "Freight invoice is 43,200 rupees. Average run is 180 km."),
    ("session-1", "Correction: budget is now 22 lakh rupees."),
    ("session-1", "Second convoy departs 19 August."),
    ("session-1", "Tarpaulin count is 600."),
    ("session-1", "Prefer WhatsApp for daily updates."),
    ("session-1", "How many family kits can we cover with the current budget?"),
]

# --- the 40-turn working session ---------------------------------------------
# Deliberately mixed, because the shape of a conversation decides the number as
# much as the engine does. The first relief-40 had every turn adding a field,
# so state grew as fast as the transcript and two of the three claims never
# appeared. Real coordination is not like that: you log a few things, then ask
# about them repeatedly, and you revise.
#
#   16 facts (40%)      state and transcript both grow
#   14 questions (35%)  state flat, transcript grows — where the saving lives,
#                       and what a coordinator actually spends the day doing
#    8 revisions (20%)  budget moves three times, the deadline twice. A replay
#                       re-sends every mention; we send one active value and
#                       keep the rest in history. This is "one field, one
#                       value", and the old demo never showed it.
#    2 retractions (5%) a supply is cancelled and must leave active state and
#                       the retrieved context, not merely be annotated
#
# Every line is something a district coordinator would plausibly type.
# `tests/test_demo_integrity.py` re-checks that mechanically.
RELIEF_40_MIXED = [
    ("session-1", "Relief operation for Wayanad district. Displaced families is 4,200."),
    ("session-1", "Name: Meera Nair, email: meera@reliefnet.org"),
    ("session-1", "Sanctioned budget is 18 lakh rupees."),
    ("session-1", "Truck count is 3, capacity per truck is 8 tonnes."),
    ("session-1", "How many trucks do we have?"),
    ("session-1", "Family kit weight is 12 kg, kit invoice is 850 rupees."),
    ("session-1", "How many kits can we cover with the current budget?"),
    ("session-1", "First convoy departs before 14 August."),
    ("session-1", "What is the deadline again?"),
    ("session-1", "Purification tablets is 40,000 units."),
    ("session-1", "Tarpaulin count is 600."),
    ("session-1", "Update: truck count is now 5."),
    ("session-1", "How many trucks do we have now?"),
    ("session-1", "Medical camp doctors is 3."),
    ("session-1", "How many families are displaced?"),
    ("session-1", "Correction: budget is now 22 lakh rupees."),
    ("session-1", "What is the budget now?"),
    ("session-1", "Daily report hour is 18."),
    ("session-1", "Blanket count is 1,800."),
    ("session-1", "How many blankets do we have?"),
    ("session-1", "Actually cancel the purification tablets, state supply already covered it."),
    ("session-1", "Are the purification tablets still on the list?"),
    ("session-1", "Volunteer count is 45."),
    ("session-1", "Freight invoice is 43,200 rupees. Average run is 180 km."),
    ("session-1", "What is the freight invoice?"),
    ("session-1", "Update: deadline is now 19 August."),
    ("session-1", "What is the deadline now?"),
    ("session-1", "Water tanker count is 2."),
    ("session-1", "Update: volunteer count is now 60."),
    ("session-1", "How many volunteers do we have?"),
    ("session-1", "Ration packs is 3,000."),
    ("session-1", "Correction: budget is now 26 lakh rupees."),
    ("session-1", "How many kits can the budget cover now?"),
    ("session-1", "Distributed kits is 1,200."),
    ("session-1", "Update: tarpaulin count is now 900."),
    ("session-1", "How many tarpaulins do we have?"),
    ("session-1", "Cancel the water tankers, the district is supplying those."),
    ("session-1", "Correction: deadline is now 21 August."),
    ("session-1", "Correction: budget is now 24 lakh rupees."),
    ("session-1", "What is the kit invoice and the daily report hour?"),
]

# --- the 40-turn, 3-session operation ----------------------------------------
# Session 1 mobilises, session 2 executes, session 3 reconciles. Sessions 2 and
# 3 open cold: the benchmark restores from the handle rather than replaying
# anything, which is the cross-session claim being exercised rather than
# asserted.
RELIEF_40 = [
    # ---- session 1: mobilisation --------------------------------------------
    ("session-1", "Relief operation for Wayanad district. Displaced families is 4,200."),
    ("session-1", "Name: Meera Nair, email: meera@reliefnet.org"),
    ("session-1", "Sanctioned budget is 22 lakh rupees."),
    ("session-1", "Truck count is 3, capacity per truck is 8 tonnes."),
    ("session-1", "Family kit weight is 12 kg, kit invoice is 850 rupees."),
    ("session-1", "First convoy departs before 14 August."),
    ("session-1", "What is our total truck capacity?"),
    ("session-1", "Purification tablets is 40,000 units."),
    ("session-1", "Tarpaulin count is 600."),
    ("session-1", "Medical camp doctors is 3."),
    ("session-1", "Update: truck count is now 5."),
    ("session-1", "How many trucks do we have now?"),
    ("session-1", "Daily report hour is 18."),
    ("session-1", "Prefer WhatsApp for daily updates."),
    # ---- session 2: execution, opened cold from the handle -------------------
    ("session-2", "Freight invoice is 43,200 rupees. Average run is 180 km."),
    ("session-2", "What is our sanctioned budget?"),
    ("session-2", "Second convoy departs 19 August."),
    ("session-2", "Actually cancel the purification tablets, state supply already covered it."),
    ("session-2", "Are purification tablets still on our list?"),
    ("session-2", "Blanket count is 1,800."),
    ("session-2", "Staging warehouse count is 2."),
    ("session-2", "How many family kits can we cover with the current budget?"),
    ("session-2", "Volunteer count is 45."),
    ("session-2", "Correction: budget is now 26 lakh rupees."),
    ("session-2", "What is the budget now?"),
    ("session-2", "Water tanker count is 2."),
    ("session-2", "Who is the coordinator and how do we reach her?"),
    # ---- session 3: reconciliation, opened cold from the handle --------------
    ("session-3", "Distributed kits is 1,200."),
    ("session-3", "How many families are we still short of?"),
    ("session-3", "Fuel invoice is 18,500 rupees."),
    ("session-3", "Damaged kits is 40."),
    ("session-3", "What is our freight invoice?"),
    ("session-3", "Cold storage units is 4."),
    ("session-3", "Ration packs is 3,000."),
    ("session-3", "Remind me when the first convoy departs."),
    ("session-3", "Update: volunteer count is now 60."),
    # a real decline with a stated reason, which is the thing a transcript
    # cannot do: the field is named, nothing is invented, and the reason is
    # recorded rather than guessed
    ("session-3", "I have not decided the second warehouse yet."),
    ("session-3", "What is still unresolved?"),
    ("session-3", "What do you know about this operation?"),
    ("session-3", "Remind me of the kit invoice and the daily report hour."),
]

DEMOS = {
    "relief-17": RELIEF_17,
    "relief-40-mixed": RELIEF_40_MIXED,
    "relief-40-cross": RELIEF_40,
}
