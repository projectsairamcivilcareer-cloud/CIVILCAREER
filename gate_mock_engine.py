"""Original, syllabus-bounded GATE Civil mock-test generation data.
# GATE mock policy: 180 minutes and 100 marks fixed; question count varies by attempt."""

from collections import Counter
import random
import re
import secrets

from gate_question_bank_extra import GATE_QUESTION_BANK_EXTRA
from gate_pyq_bank import GATE_PYQ_BANK


GATE_SUBJECTS = [
    "Engineering Mathematics",
    "Engineering Mechanics",
    "Solid Mechanics",
    "Structural Analysis",
    "Concrete Structures",
    "Steel Structures",
    "Geotechnical Engineering",
    "Fluid Mechanics",
    "Hydraulics",
    "Hydrology",
    "Irrigation",
    "Environmental Engineering",
    "Transportation Engineering",
    "Geomatics Engineering",
    "Construction Materials and Management",
]


GATE_MOCK_PROFILES = {
    # GATE CE paper structure used for automatic Civil Career mock generation.
    # Official GATE 2026: 10 GA questions (15 marks) + 55 subject questions (85 marks).
    # CE subject component includes Engineering Mathematics (13 marks) + Civil subject (72 marks).
    "short": {