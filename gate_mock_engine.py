"""Original, syllabus-bounded GATE Civil mock-test generation data.
# GATE mock policy: 180 minutes and 100 marks fixed; question count varies by attempt."""

from collections import Counter
import random
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
    # GATE-style Civil Engineering paper: 65 questions, 100 marks.
    # 10 GA + 7 Engineering Mathematics + 48 Civil Core.
    "short": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
    "standard": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
    "full": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
    "difficult": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
    "expert": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
    "elite": {"math_questions": 7, "core_questions": 48, "aptitude_questions": 10, "total_marks": 100},
}


def allocate_question_marks(question_count, total_marks):
    """Return the required one-mark and two-mark counts for a target total."""
    one_mark = 2 * question_count - total_marks
    two_mark = total_marks - question_count
    if one_mark < 0 or two_mark < 0 or one_mark + two_mark != question_count:
        raise ValueError("A 100-mark mock needs a valid question count and 1/2-mark mix")
    return {"one_mark": one_mark, "two_mark": two_mark, "total_marks": total_marks}


def gate_mock_structure(profile="full"):
    settings = GATE_MOCK_PROFILES.get(profile, GATE_MOCK_PROFILES["full"])
    total_questions = sum(settings[key] for key in ("math_questions", "core_questions", "aptitude_questions"))
    return {**settings, "total_questions": total_questions, "marks": allocate_question_marks(total_questions, settings["total_marks"])}


GATE_APTITUDE_QUESTIONS = [
    {"question": "A contractor completes 3/5 of a task in 12 days at a constant rate. The remaining task takes ___ days.", "option_a": "6", "option_b": "8", "option_c": "10", "option_d": "12", "correct_answer": "B", "subject": "General Aptitude", "topic": "Numerical Ability", "subtopic": "Ratios and proportions", "question_type": "mcq", "difficulty_level": "L2", "difficulty_rating": 2, "marks": 1, "estimated_time": 1.0, "explanation": "The completed rate is 1/20 task per day, so 2/5 requires 8 days.", "solution": "12 divided by 3/5 = 20 days total; remaining time = 8 days.", "concept": "Work-rate proportion", "formula": "time = work / rate"},
    {"question": "The average of five readings is 24. If one reading 18 is replaced by 28, the new average is:", "option_a": "24", "option_b": "25", "option_c": "26", "option_d": "28", "correct_answer": "C", "subject": "General Aptitude", "topic": "Numerical Ability", "subtopic": "Averages", "question_type": "mcq", "difficulty_level": "L2", "difficulty_rating": 2, "marks": 1, "estimated_time": 1.0, "explanation": "The total increases by 10 across five readings.", "solution": "New average = 24 + (28-18)/5 = 26.", "concept": "Effect of replacement on average", "formula": "new mean = old mean + change/n"},
    {"question": "If x + 1/x = 5 for positive x, then x2 + 1/x2 is:", "option_a": "23", "option_b": "25", "option_c": "27", "option_d": "29", "correct_answer": "A", "subject": "General Aptitude", "topic": "Numerical Ability", "subtopic": "Algebra", "question_type": "mcq", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 2, "estimated_time": 1.5, "explanation": "Squaring introduces twice the product term.", "solution": "(x+1/x)^2 = x2+2+1/x2, hence the result is 25-2=23.", "concept": "Algebraic identity", "formula": "(a+b)^2=a^2+2ab+b^2"},
    {"question": "A machine produces 2% defective components. In 100 independent components, the expected number of defectives is ___ .", "option_a": "0.2", "option_b": "2", "option_c": "20", "option_d": "50", "correct_answer": "2", "answer": 2, "subject": "General Aptitude", "topic": "Probability", "subtopic": "Expectation", "question_type": "nat", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 1, "estimated_time": 1.0, "explanation": "Expected count is n times the defect probability.", "solution": "E[X] = 100(0.02)=2.", "concept": "Binomial expectation", "formula": "E[X]=np"},
    {"question": "The next term in the sequence 2, 6, 12, 20, 30 is:", "option_a": "36", "option_b": "40", "option_c": "42", "option_d": "44", "correct_answer": "C", "subject": "General Aptitude", "topic": "Analytical Reasoning", "subtopic": "Number series", "question_type": "mcq", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 1, "estimated_time": 1.0, "explanation": "Terms are n(n+1) for n from 1 onward.", "solution": "6(7)=42.", "concept": "Pattern recognition", "formula": "a_n=n(n+1)"},
    {"question": "A statement says: all surveyed bridges are inspected, and some inspected bridges are old. Which conclusion is necessarily true?", "option_a": "All surveyed bridges are old", "option_b": "Some old bridges are inspected", "option_c": "No inspected bridge is new", "option_d": "All old bridges are surveyed", "correct_answer": "B", "subject": "General Aptitude", "topic": "Analytical Reasoning", "subtopic": "Statements and conclusions", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 2, "estimated_time": 2.0, "explanation": "The second premise directly establishes that some inspected bridges are old.", "solution": "Only the existential conclusion in option B follows.", "concept": "Logical implication", "formula": "A subset relation does not imply equivalence"},
    {"question": "A 4-digit code uses distinct digits from 1, 2, 3, 4, and 5. The number of possible codes divisible by 5 is ___ .", "option_a": "12", "option_b": "24", "option_c": "48", "option_d": "60", "correct_answer": "24", "answer": 24, "subject": "General Aptitude", "topic": "Combinatorics", "subtopic": "Permutations", "question_type": "nat", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 2, "estimated_time": 2.0, "explanation": "Divisibility by 5 fixes the last digit as 5; the other three positions are a permutation of four remaining digits.", "solution": "4P3 = 4*3*2 = 24.", "concept": "Restricted permutations", "formula": "nPr=n!/(n-r)!"},
    {"question": "A data set has median 18. If every observation is transformed as y=3x-2, the new median is:", "option_a": "16", "option_b": "52", "option_c": "54", "option_d": "56", "correct_answer": "B", "subject": "General Aptitude", "topic": "Data Interpretation", "subtopic": "Measures of central tendency", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 1, "estimated_time": 1.0, "explanation": "A positive linear transformation maps the median using the same equation.", "solution": "3(18)-2=52.", "concept": "Linear transformation of data", "formula": "median(aX+b)=a median(X)+b"},
    {"question": "If the probability that a component survives one year is 0.9, assuming independence, the probability that exactly two of three components survive is:", "option_a": "0.027", "option_b": "0.081", "option_c": "0.243", "option_d": "0.729", "correct_answer": "C", "subject": "General Aptitude", "topic": "Probability", "subtopic": "Binomial probability", "question_type": "mcq", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 2, "estimated_time": 2.0, "explanation": "Choose which two survive and multiply the corresponding probabilities.", "solution": "C(3,2)(0.9)^2(0.1)=0.243.", "concept": "Binomial event probability", "formula": "P(X=k)=C(n,k)p^k(1-p)^(n-k)"},
    {"question": "A word is encoded by shifting each letter three positions forward cyclically. The encoding of CIVIL begins with:", "option_a": "FL", "option_b": "F L", "option_c": "ZLY", "option_d": "F M", "correct_answer": "A", "subject": "General Aptitude", "topic": "Verbal Ability", "subtopic": "Coding and decoding", "question_type": "mcq", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 1, "estimated_time": 1.5, "explanation": "C shifted three places forward is F, and I shifted three places is L.", "solution": "C->F and I->L, so the encoded word begins FL.", "concept": "Cyclic letter shift", "formula": "encoded position=(position+3) mod 26"},
]


GATE_SYLLABUS_2025 = [
    {"subject": "Engineering Mathematics", "topics": [
        "Linear Algebra: Matrix algebra; Systems of linear equations; eigen values and eigen vectors.",
        "Calculus: Functions of single variable; Limit, continuity and differentiability; Mean value theorems, local maxima and minima; Taylor series; Evaluation of definite and indefinite integrals, application of definite integral to obtain area and volume; Partial derivatives; Total derivative; Gradient, Divergence and Curl, Vector identities; Directional derivatives; Line, Surface and Volume integrals.",
        "Ordinary Differential Equation (ODE): First order (linear and non-linear) equations; higher order linear equations with constant coefficients; Euler-Cauchy equations; initial and boundary value problems.",
        "Partial Differential Equation (PDE): Fourier series; Separation of variables; solutions of one-dimensional diffusion equation; first and second order one-dimensional wave equation and two-dimensional Laplace equation.",
        "Probability and Statistics: Sampling theorems; Conditional probability; Descriptive statistics – Mean, median, mode and standard deviation; Random Variables – Discrete and Continuous, Poisson and Normal Distribution; Linear regression.",
        "Numerical Methods: Error analysis. Numerical solutions of linear and non-linear algebraic equations; Newton’s and Lagrange polynomials; numerical differentiation; Integration by trapezoidal and Simpson’s rule; Single and multi-step methods for first order differential equations.",
    ]},
    {"subject": "Structural Engineering", "topics": [
        "Engineering Mechanics: System of forces, free-body diagrams, equilibrium equations; Internal forces in structures; Frictions and its applications; Centre of mass; Free Vibrations of undamped SDOF system.",
        "Solid Mechanics: Bending moment and shear force in statically determinate beams; Simple stress and strain relationships; Simple bending theory, flexural and shear stresses, shear centre; Uniform torsion, Transformation of stress; buckling of column, combined and direct bending stresses.",
        "Structural Analysis: Statically determinate and indeterminate structures by force/energy methods; Method of superposition; Analysis of trusses, arches, beams, cables and frames; Displacement methods: Slope deflection and moment distribution methods; Influence lines; Stiffness and flexibility methods of structural analysis.",
        "Construction Materials and Management: Construction Materials: Structural Steel – Composition, material properties and behaviour; Concrete - Constituents, mix design, short-term and long-term properties. Construction Management: Types of construction projects; Project planning and network analysis - PERT and CPM; Cost estimation.",
        "Concrete Structures: Working stress and Limit state design concepts; Design of beams, slabs, columns; Bond and development length; Prestressed concrete beams.",
        "Steel Structures: Working stress and Limit state design concepts; Design of tension and compression members, beams and beam-columns, column bases; Connections - simple and eccentric, beam-column connections, plate girders and trusses; Concept of plastic analysis - beams and frames.",
    ]},
    {"subject": "Geotechnical Engineering", "topics": [
        "Soil Mechanics: Three-phase system and phase relationships, index properties; Unified and Indian standard soil classification system; Permeability - one dimensional flow, Seepage through soils – two-dimensional flow, flow nets, uplift pressure, piping, capillarity, seepage force; Principle of effective stress and quicksand condition; Compaction of soils; One-dimensional consolidation, time rate of consolidation; Shear Strength, Mohr’s circle, effective and total shear strength parameters, Stress-Strain characteristics of clays and sand; Stress paths.",
        "Foundation Engineering: Sub-surface investigations - Drilling bore holes, sampling, plate load test, standard penetration and cone penetration tests; Earth pressure theories - Rankine and Coulomb; Stability of slopes – Finite and infinite slopes, Bishop’s method; Stress distribution in soils – Boussinesq’s theory; Pressure bulbs, Shallow foundations – Terzaghi’s and Meyerhoff’s bearing capacity theories, effect of water table; Combined footing and raft foundation; Contact pressure; Settlement analysis in sands and clays; Deep foundations – dynamic and static formulae, Axial load capacity of piles in sands and clays, pile load test, pile under lateral loading, pile group efficiency, negative skin friction.",
    ]},
    {"subject": "Water Resources Engineering", "topics": [
        "Fluid Mechanics: Properties of fluids, fluid statics; Continuity, momentum and energy equations and their applications; Potential flow, Laminar and turbulent flow; Flow in pipes, pipe networks; Concept of boundary layer and its growth; Concept of lift and drag.",
        "Hydraulics: Forces on immersed bodies; Flow measurement in channels and pipes; Dimensional analysis and hydraulic similitude; Channel Hydraulics - Energy-depth relationships, specific energy, critical flow, hydraulic jump, uniform flow, gradually varied flow and water surface profiles.",
        "Hydrology: Hydrologic cycle, precipitation, evaporation, evapo-transpiration, watershed, infiltration, unit hydrographs, hydrograph analysis, reservoir capacity, flood estimation and routing, surface run-off models, ground water hydrology - steady state well hydraulics and aquifers; Application of Darcy’s Law.",
        "Irrigation: Types of irrigation systems and methods; Crop water requirements - Duty, delta, evapotranspiration; Gravity Dams and Spillways; Lined and unlined canals, Design of weirs on permeable foundation; cross drainage structures.",
    ]},
    {"subject": "Environmental Engineering", "topics": [
        "Water and Waste Water Quality and Treatment: Basics of water quality standards – Physical, chemical and biological parameters; Water quality index; Unit processes and operations; Water requirement; Water distribution system; Drinking water treatment.",
        "Sewerage system design, quantity of domestic wastewater, primary and secondary treatment. Effluent discharge standards; Sludge disposal; Reuse of treated sewage for different applications.",
        "Air Pollution: Types of pollutants, their sources and impacts, air pollution control, air quality standards, Air quality Index and limits.",
        "Municipal Solid Wastes: Characteristics, generation, collection and transportation of solid wastes, engineered systems for solid waste management (reuse/recycle, energy recovery, treatment and disposal).",
    ]},
    {"subject": "Transportation Engineering", "topics": [
        "Transportation Infrastructure: Geometric design of highways - cross-sectional elements, sight distances, horizontal and vertical alignments.",
        "Geometric design of railway Track – Speed and Cant.",
        "Concept of airport runway length, calculations and corrections; taxiway and exit taxiway design.",
        "Highway Pavements: Highway materials - desirable properties and tests; Desirable properties of bituminous paving mixes; Design factors for flexible and rigid pavements; Design of flexible and rigid pavement using IRC codes.",
        "Traffic Engineering: Traffic studies on flow and speed, peak hour factor, accident study, statistical analysis of traffic data; Microscopic and macroscopic parameters of traffic flow, fundamental relationships; Traffic signs; Signal design by Webster’s method; Types of intersections; Highway capacity.",
    ]},
    {"subject": "Geomatics Engineering", "topics": [
        "Principles of surveying; Errors and their adjustment; Maps - scale, coordinate system; Distance and angle measurement - Levelling and trigonometric levelling; Traversing and triangulation survey; Total station; Horizontal and vertical curves.",
        "Photogrammetry and Remote Sensing - Scale, flying height; Basics of remote sensing and GIS.",
    ]},
]


GATE_SYLLABUS_2027 = [
    {"subject": "General Aptitude", "topics": [
        "Verbal Aptitude: Basic English grammar; basic vocabulary; words, idioms and phrases in context; reading comprehension; narrative sequencing.",
        "Quantitative Aptitude: Data interpretation using graphs, plots, maps and tables; numerical computation and estimation; ratios, percentages, powers, exponents and logarithms; permutations and combinations; series; mensuration and geometry; elementary statistics and probability.",
        "Analytical Aptitude: Logic, deduction and induction, analogy, numerical relations and reasoning.",
        "Spatial Aptitude: Transformation of shapes including translation, rotation, scaling, mirroring, assembling and grouping; paper folding, cutting and patterns in two and three dimensions.",
    ]},
    {"subject": "Engineering Mathematics", "topics": [
        "Linear Algebra: Matrix algebra; systems of linear equations; eigenvalues and eigenvectors.",
        "Calculus: Functions of single variable; limits, continuity and differentiability; mean value theorems; local maxima and minima; Taylor series; definite and indefinite integrals; applications of definite integrals to area and volume; partial and total derivatives; gradient, divergence and curl; vector identities; directional derivatives; line, surface and volume integrals.",
        "Ordinary Differential Equations: First-order linear and nonlinear equations; higher-order linear equations with constant coefficients; Euler-Cauchy equations; initial and boundary value problems.",
        "Partial Differential Equations: Fourier series; separation of variables; one-dimensional diffusion equation; first- and second-order one-dimensional wave equations; two-dimensional Laplace equation.",
        "Probability and Statistics: Basic probability concepts, axioms and theorems, statistical independence, conditional probability; descriptive statistics including mean, median, mode and standard deviation; random variables; probability mass function, probability density function and cumulative distribution function; Poisson and normal distributions; linear regression.",
        "Numerical Methods: Error analysis; numerical solutions of linear and nonlinear algebraic equations; Newton and Lagrange polynomials; numerical differentiation; trapezoidal and Simpson's integration; single- and multi-step methods for first-order differential equations.",
    ]},
    {"subject": "Structural Engineering", "topics": [
        "Engineering Mechanics: System of forces, free-body diagrams, equilibrium equations, internal forces in structures, friction and its applications, and centre of mass.",
        "Solid Mechanics: Bending moment and shear force in statically determinate beams; transformation of stress including Mohr's circle; simple stress and strain relationships; simple bending theory; flexural and shear stresses; shear centre; uniform torsion; combined stresses; column buckling.",
        "Structural Analysis: Principle of superposition; work and energy methods including principle of virtual work and Castigliano's second theorem; deflections of statically determinate beams, frames and trusses; analysis of statically indeterminate structures by force and displacement methods including method of consistent deformations, slope-deflection and moment distribution; influence lines and moving loads; stiffness matrix method; analysis of determinate arches and cables.",
        "Concrete Structures: Working stress and limit state design concepts; design and detailing of beams, slabs, columns and isolated footings; bond and development length.",
        "Steel Structures: Working stress and limit state design concepts; design of tension and compression members, beams, beam-columns and column bases; simple and eccentric connections and beam-column connections; plastic analysis of beams and portal frames.",
    ]},
    {"subject": "Geotechnical Engineering", "topics": [
        "Three-phase system and phase relationships; index properties; Unified and Indian Standard soil classification; permeability and one-dimensional flow; seepage through soils, two-dimensional flow and flow nets; uplift pressure, piping, capillarity and seepage force; effective stress and quicksand condition; compaction; one-dimensional consolidation and time rate; shear strength, Mohr's circle, effective and total shear strength parameters; stress-strain characteristics of clays and sand; stress paths.",
        "Sub-surface investigations including drilling bore holes, sampling, plate load test, standard penetration test and cone penetration test; earth pressure theories by Rankine and Coulomb; slope stability for finite and infinite slopes using Bishop's method; sheet piles; Boussinesq stress distribution and pressure bulbs; shallow foundations including Terzaghi and Meyerhof bearing capacity and water-table effects; combined and raft foundations; contact pressure; settlement analysis in sands and clays; deep foundations including static formulae, axial load capacity of piles in sands and clays, pile load test, lateral loading, pile group efficiency and negative skin friction; ground improvement techniques.",
    ]},
    {"subject": "Water Resources Engineering", "topics": [
        "Fluid Mechanics: Properties of fluids and fluid statics; continuity, momentum and energy equations and applications; potential flow; laminar and turbulent flow; flow in pipes and pipe networks; boundary-layer growth; lift and drag.",
        "Hydraulics: Forces on immersed bodies; flow measurement in channels and pipes; dimensional analysis and hydraulic similitude; prismatic and mobile channels; energy-depth relationships and specific energy; critical flow; steady and unsteady flow; rapidly varied flow and hydraulic jump; gradually varied flow and water-surface profiles; flow past sharp-crested weirs.",
        "Hydrology: Hydrologic cycle, precipitation, evaporation, evapotranspiration and watershed; infiltration; streamflow measurement; unit hydrographs; hydrograph analysis; reservoir capacity; flood estimation and routing; surface-runoff models; groundwater hydrology including steady-state well hydraulics and aquifers; Darcy's law.",
        "Irrigation: Types of irrigation systems and methods; crop water requirements, duty, delta and evapotranspiration; gravity dams and spillways; lined and unlined canals; design of weirs on permeable foundations; cross-drainage structures; river training structures; earthen dams; seepage through dams; well irrigation.",
    ]},
    {"subject": "Environmental Engineering", "topics": [
        "Water and Wastewater Quality and Treatment: Water-quality standards; physical, chemical and biological parameters; water quality index; unit processes and operations; water requirement; water distribution system; drinking-water treatment; sewerage system design; quantity of domestic wastewater; primary and secondary treatment; effluent discharge standards; sludge disposal; reuse of treated sewage.",
        "Air Pollution: Types of pollutants, their sources and impacts; air-pollution control; air-quality standards; Air Quality Index and limits.",
        "Municipal Solid Wastes: Characteristics, generation, collection and transportation; engineered systems for solid-waste management including reuse/recycle, energy recovery, treatment and disposal.",
    ]},
    {"subject": "Transportation Engineering", "topics": [
        "Transportation Infrastructure: Geometric design of highways including cross-sectional elements, sight distances, horizontal and vertical alignments; geometric design of railway track including speed and cant; airport runway length, calculations and corrections; taxiway and exit taxiway design.",
        "Highway Pavements: Highway materials, desirable properties and tests; desirable properties of bituminous paving mixes; design factors for flexible and rigid pavements; design of flexible and rigid pavement using IRC codes.",
        "Traffic Engineering: Traffic studies on flow and speed, peak hour factor, accident study, statistical analysis of traffic data; microscopic and macroscopic traffic-flow parameters and fundamental relationships; traffic signs; signal design by Webster's method; types of intersections and interchanges; highway capacity and level of service.",
        "Transportation Planning: Four-step travel demand modelling including trip generation, trip distribution, mode choice and traffic assignment and its applications.",
    ]},
    {"subject": "Geomatics Engineering", "topics": [
        "Surveying: Principles of surveying; plane and geodetic surveying; GNSS surveying; errors and their adjustment; maps, scale and coordinate system; distance and angle measurement; levelling and trigonometric levelling; traversing and triangulation survey; total station; principles of topographic, cadastral and engineering surveys; introduction to cartography and map projections.",
        "Photogrammetry: Introduction to photogrammetry; digital photogrammetry; photographic scale and flying height; space resection; parallax equations; elevations by parallax differences; camera calibration.",
    ]},
    {"subject": "Construction Materials and Management", "topics": [
        "Construction Materials: Steel composition, material properties and behaviour; cement composition, hydration and microstructure, chemical and mineral admixtures; concrete constituents, mix design, short-term and long-term properties.",
        "Construction Management: Types of construction projects; estimation and costing using long-wall and short-wall methods, centre-line method and analysis of rates; project planning and scheduling using AOA and AON network analysis, PERT and CPM; project updating and monitoring; construction equipment for earthwork, concreting, hoisting and transportation of materials; types of contracts.",
    ]},
]

# Keep the year selector backward-compatible. The current Civil syllabus is stored in
# GATE_SYLLABUS_2027; use the same syllabus for the 2026 fallback instead of
# crashing the production app when an older year is requested.
GATE_SYLLABUS_2026 = GATE_SYLLABUS_2027

GATE_SYLLABI = {"2025": GATE_SYLLABUS_2025, "2026": GATE_SYLLABUS_2026, "2027": GATE_SYLLABUS_2027}
GATE_SYLLABUS = GATE_SYLLABUS_2027


GATE_QUESTION_BANK = [
    {"question": "For the matrix A = [[2, 1], [1, 2]], the eigenvalue associated with the eigenvector [1, 1] is:", "option_a": "1", "option_b": "2", "option_c": "3", "option_d": "4", "correct_answer": "C", "subject": "Engineering Mathematics", "topic": "Linear Algebra", "subtopic": "Eigenvalues and eigenvectors", "question_type": "mcq", "difficulty_level": "L1", "difficulty_rating": 1, "marks": 1, "estimated_time": 1.0, "explanation": "Multiplication by A gives [3, 3], which is 3[1, 1].", "solution": "A[1,1]^T = [3,3]^T = 3[1,1]^T.", "concept": "Eigenvector scaling", "formula": "Av = lambda v"},
    {"question": "A simply supported beam has a central point load P. Which statements are correct?", "option_a": "The bending moment is maximum at midspan", "option_b": "The bending moment at each support is zero", "option_c": "The shear force changes sign at midspan", "option_d": "The reactions are P/2 for unequal support stiffness", "correct_answer": ["A", "B", "C"], "subject": "Structural Analysis", "topic": "Determinate beams", "subtopic": "Shear force and bending moment", "question_type": "msq", "difficulty_level": "L2", "difficulty_rating": 2, "marks": 2, "estimated_time": 1.5, "explanation": "Symmetry gives equal reactions and the shear reverses at the load; ideal pin and roller supports have zero moment.", "solution": "RA = RB = P/2 and Mmax = PL/4 at midspan.", "concept": "Beam equilibrium and diagrams", "formula": "Mmax = PL/4"},
    {"question": "A soil has total vertical stress 180 kPa and pore-water pressure 70 kPa. Its effective stress is ___ kPa.", "option_a": "70", "option_b": "110", "option_c": "180", "option_d": "250", "correct_answer": "110", "answer": 110, "subject": "Geotechnical Engineering", "topic": "Effective stress", "subtopic": "Principle of effective stress", "question_type": "nat", "difficulty_level": "L2", "difficulty_rating": 2, "marks": 1, "estimated_time": 1.0, "explanation": "Effective stress is total stress less pore pressure.", "solution": "sigma' = 180 - 70 = 110 kPa.", "concept": "Effective stress", "formula": "sigma' = sigma - u"},
    {"question": "For steady incompressible flow through a pipe that contracts from area 0.04 m2 to 0.01 m2, if the upstream velocity is 2 m/s, the downstream velocity is:", "option_a": "0.5 m/s", "option_b": "2 m/s", "option_c": "4 m/s", "option_d": "8 m/s", "correct_answer": "D", "subject": "Fluid Mechanics", "topic": "Continuity", "subtopic": "One-dimensional flow", "question_type": "mcq", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 1, "estimated_time": 1.5, "explanation": "Discharge is conserved, so velocity increases inversely with area.", "solution": "V2 = A1V1/A2 = 0.04(2)/0.01 = 8 m/s.", "concept": "Continuity equation", "formula": "A1V1 = A2V2"},
    {"question": "A triangular drainage channel has side slope 1H:1V and carries 8 m3/s at critical flow. Using g = 10 m/s2, the critical depth is approximately ___ m.", "option_a": "0.82", "option_b": "1.26", "option_c": "1.64", "option_d": "2.34", "correct_answer": "1.26", "answer": 1.26, "subject": "Hydraulics", "topic": "Open channel flow", "subtopic": "Critical flow", "question_type": "nat", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 2, "estimated_time": 2.5, "explanation": "For a symmetric triangular section, Q2 T = g A3 and A=y2, T=2y, giving y5=Q2/(2g).", "solution": "y = [64/20]^(1/5) = 1.26 m.", "concept": "Critical depth from specific energy", "formula": "Q2 T = g A3"},
    {"question": "A concrete mix has water content 180 kg/m3 and water-cement ratio 0.45. The cement content is ___ kg/m3.", "option_a": "81", "option_b": "225", "option_c": "400", "option_d": "810", "correct_answer": "400", "answer": 400, "subject": "Construction Materials and Management", "topic": "Concrete", "subtopic": "Mix proportions", "question_type": "nat", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 1, "estimated_time": 1.5, "explanation": "The water-cement ratio is the mass ratio of water to cement.", "solution": "C = 180/0.45 = 400 kg/m3.", "concept": "Water-cement ratio", "formula": "w/c = W/C"},
    {"question": "In a level survey, the backsight and foresight are 1.825 m and 2.430 m respectively. The second point is:", "option_a": "0.605 m higher", "option_b": "0.605 m lower", "option_c": "4.255 m higher", "option_d": "4.255 m lower", "correct_answer": "B", "subject": "Geomatics Engineering", "topic": "Levelling", "subtopic": "Rise and fall", "question_type": "mcq", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 1, "estimated_time": 1.5, "explanation": "The change in level is BS minus FS, which is negative here.", "solution": "RL2 - RL1 = BS - FS = -0.605 m.", "concept": "Height difference", "formula": "Delta RL = BS - FS"},
    {"question": "For a normally consolidated clay, which statements about one-dimensional consolidation are correct?", "option_a": "Primary consolidation is caused by drainage of pore water", "option_b": "Effective stress increases as excess pore pressure dissipates", "option_c": "Total stress remains constant during a drained loading increment", "option_d": "Secondary compression is completed before primary consolidation", "correct_answer": ["A", "B", "C"], "subject": "Geotechnical Engineering", "topic": "Consolidation", "subtopic": "Time rate and settlement", "question_type": "msq", "difficulty_level": "L3", "difficulty_rating": 3, "marks": 2, "estimated_time": 2.0, "explanation": "With constant applied total stress, dissipation of excess pore pressure transfers stress to the soil skeleton.", "solution": "Use sigma = sigma' + u; as u decreases, sigma' increases.", "concept": "Consolidation mechanism", "formula": "Tv = cv t/Hdr2"},
    {"question": "A 6 m high retaining wall retains level sand with unit weight 18 kN/m3 and phi=30 degrees. For Rankine active pressure, the resultant thrust per metre length is:", "option_a": "54 kN/m", "option_b": "72 kN/m", "option_c": "108 kN/m", "option_d": "162 kN/m", "correct_answer": "C", "subject": "Geotechnical Engineering", "topic": "Earth pressure", "subtopic": "Rankine active pressure", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 2, "estimated_time": 2.5, "explanation": "For phi=30 degrees, Ka=(1-sin phi)/(1+sin phi)=1/3.", "solution": "Pa = 0.5 gamma H2 Ka = 0.5(18)(36)(1/3)=108 kN/m.", "concept": "Active earth pressure", "formula": "Pa = 1/2 gamma H2 Ka"},
    {"question": "A rectangular open channel is flowing uniformly. If its width is doubled while discharge and roughness remain fixed, the normal depth will:", "option_a": "Increase because wetted perimeter increases", "option_b": "Decrease because hydraulic radius changes", "option_c": "Remain exactly unchanged", "option_d": "Become critical automatically", "correct_answer": "B", "subject": "Hydraulics", "topic": "Uniform flow", "subtopic": "Manning equation", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 1, "estimated_time": 2.0, "explanation": "For a fixed discharge, the wider section conveys flow at a smaller depth under the Manning relation.", "solution": "Solve Q=(1/n)AR^(2/3)S^(1/2) before and after changing b; y reduces.", "concept": "Normal depth", "formula": "Q = (1/n) A R^(2/3) S^(1/2)"},
    {"question": "A unit hydrograph of duration 2 h has peak 40 m3/s. A 4 h unit hydrograph is obtained by superposing two 2 h unit hydrographs separated by 2 h. Its peak cannot be determined from the given peak alone because:", "option_a": "The ordinates must be averaged", "option_b": "The time distribution of the ordinates is required", "option_c": "Unit hydrographs cannot be superposed", "option_d": "The catchment area is irrelevant", "correct_answer": "B", "subject": "Hydrology", "topic": "Unit hydrograph", "subtopic": "S-curve and superposition", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 1, "estimated_time": 2.0, "explanation": "Superposition is ordinate-by-ordinate; a single peak does not describe the full hydrograph.", "solution": "Shift and add every ordinate of the 2 h hydrograph, not only its maximum.", "concept": "Hydrograph transformation", "formula": "Qtotal(t) = Q1(t) + Q2(t-2)"},
    {"question": "A two-lane road has free-flow speed 80 km/h, density 20 veh/km/lane and flow 1400 veh/h/lane. The average speed from q=kv is:", "option_a": "35 km/h", "option_b": "50 km/h", "option_c": "70 km/h", "option_d": "100 km/h", "correct_answer": "C", "subject": "Transportation Engineering", "topic": "Traffic flow", "subtopic": "Macroscopic relationships", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 1, "estimated_time": 1.5, "explanation": "The flow-density relation directly gives the space-mean speed.", "solution": "v=q/k=1400/20=70 km/h.", "concept": "Fundamental traffic relation", "formula": "q = kv"},
    {"question": "In a singly reinforced rectangular RCC beam at balanced failure, increasing effective depth while retaining the same reinforcement ratio primarily increases:", "option_a": "Neutral-axis depth ratio only", "option_b": "Moment capacity approximately in proportion to d2", "option_c": "Concrete tensile strength", "option_d": "Characteristic cube strength", "correct_answer": "B", "subject": "Concrete Structures", "topic": "Limit state design", "subtopic": "Flexural capacity", "question_type": "mcq", "difficulty_level": "L4", "difficulty_rating": 4, "marks": 2, "estimated_time": 2.5, "explanation": "With a fixed reinforcement ratio and material grades, As scales with bd and lever-arm moment scales approximately with bd2.", "solution": "Mu = 0.87 fy As(d-0.42 xu); As proportional to bd and xu proportional to d.", "concept": "Scaling of beam capacity", "formula": "Mu = 0.87 fy As(d - 0.42xu)"},
    {"question": "A steel compression member is fixed at one end and hinged at the other. Its effective length factor is closest to:", "option_a": "0.5", "option_b": "0.7", "option_c": "1.0", "option_d": "2.0", "correct_answer": "B", "subject": "Steel Structures", "topic": "Compression members", "subtopic": "Column buckling", "question_type": "mcq", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 1, "estimated_time": 2.0, "explanation": "The fixed-hinged idealization has effective length approximately 0.7L.", "solution": "Use Le = KL with K approximately 0.7 for fixed-hinged end conditions.", "concept": "Elastic buckling", "formula": "Pcr = pi2 EI/Le2"},
    {"question": "A pipe network has two parallel branches between the same nodes. Which statements are correct for steady incompressible flow?", "option_a": "Head loss is equal in both branches", "option_b": "Discharges in branches add to the total discharge", "option_c": "Velocity must be equal in both branches", "option_d": "Energy grade line has the same endpoint heads", "correct_answer": ["A", "B", "D"], "subject": "Fluid Mechanics", "topic": "Pipe networks", "subtopic": "Parallel pipes", "question_type": "msq", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 2, "estimated_time": 2.5, "explanation": "Parallel branches share endpoint piezometric heads, hence the same loss; flow division depends on resistance.", "solution": "hL1=hL2 and Q=Q1+Q2; equal velocity is not required.", "concept": "Network energy balance", "formula": "hL1 = hL2; Q = sum Qi"},
    {"question": "A surveying traverse has independent angular errors with equal variance. Equal-weight adjustment of the observed angles distributes the correction:", "option_a": "In proportion to each angle magnitude", "option_b": "Equally among all angles", "option_c": "Only to the largest angle", "option_d": "Only to the closing line", "correct_answer": "B", "subject": "Geomatics Engineering", "topic": "Errors and adjustment", "subtopic": "Traverse adjustment", "question_type": "mcq", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 1, "estimated_time": 2.0, "explanation": "Equal precision observations receive equal corrections under the least-squares condition.", "solution": "For equal weights, each correction is the angular misclosure divided by n.", "concept": "Least-squares adjustment", "formula": "sum vi = -f_beta"},
    {"question": "For a saturated soil layer, the flow net has 8 flow channels and 12 potential drops. If total head loss is 6 m and k=0.0005 m/s, discharge per metre width is ___ m3/s.", "option_a": "0.00025", "option_b": "0.002", "option_c": "0.02", "option_d": "0.25", "correct_answer": "0.002", "answer": 0.002, "subject": "Geotechnical Engineering", "topic": "Seepage", "subtopic": "Flow nets", "question_type": "nat", "difficulty_level": "L5", "difficulty_rating": 5, "marks": 2, "estimated_time": 2.5, "explanation": "Flow-net discharge is k H Nf/Nd per unit width.", "solution": "q=0.0005(6)(8/12)=0.002 m3/s.", "concept": "Flow-net discharge", "formula": "q = k H Nf/Nd"},
    {"question": "A project network has activities A(3 days) and B(5 days) starting together, followed by C(4 days) after both. The critical path length is ___ days.", "option_a": "7", "option_b": "9", "option_c": "12", "option_d": "15", "correct_answer": "9", "answer": 9, "subject": "Construction Materials and Management", "topic": "Project scheduling", "subtopic": "CPM", "question_type": "nat", "difficulty_level": "L6", "difficulty_rating": 6, "marks": 2, "estimated_time": 2.0, "explanation": "The longer parallel predecessor controls the start of C.", "solution": "max(3,5)+4=9 days.", "concept": "Critical path", "formula": "EF = ES + duration"},
    {"question": "For a laminar boundary layer over a smooth flat plate, if velocity doubles and all fluid properties and length remain unchanged, the local skin-friction coefficient:", "option_a": "Doubles", "option_b": "Becomes half", "option_c": "Decreases by factor sqrt(2)", "option_d": "Remains unchanged", "correct_answer": "C", "subject": "Fluid Mechanics", "topic": "Boundary layer", "subtopic": "Laminar flat-plate flow", "question_type": "mcq", "difficulty_level": "L6", "difficulty_rating": 6, "marks": 2, "estimated_time": 2.5, "explanation": "Cf is proportional to Rex^(-1/2), and Reynolds number doubles with velocity.", "solution": "Cf,new/Cf,old=(2Re/Re)^(-1/2)=1/sqrt(2).", "concept": "Similarity scaling", "formula": "Cf,x = 0.664/sqrt(Rex)"},
    {"question": "A simply supported beam is subjected to a moving point load. The maximum bending moment at a fixed section occurs when the load is:", "option_a": "At either support only", "option_b": "At the section itself", "option_c": "At midspan regardless of section", "option_d": "At one-quarter span regardless of section", "correct_answer": "B", "subject": "Structural Analysis", "topic": "Influence lines", "subtopic": "Moving loads", "question_type": "mcq", "difficulty_level": "L7", "difficulty_rating": 7, "marks": 2, "estimated_time": 3.0, "explanation": "The influence line for bending moment at a section has its ordinate maximum at that section.", "solution": "Place the point load at the section whose moment is being maximized.", "concept": "Influence-line interpretation", "formula": "M_x = P * influence ordinate at x"},
]



def _make_source_variant(q, a, b, c, d, correct, subject, topic, subtopic, qtype="mcq", answer=None, difficulty="L3", rating=3, explanation="", solution="", concept="", formula=""):
    item = {
        "question": q, "option_a": a, "option_b": b, "option_c": c, "option_d": d,
        "correct_answer": correct, "subject": subject, "topic": topic, "subtopic": subtopic,
        "question_type": qtype, "difficulty_level": difficulty, "difficulty_rating": rating,
        "marks": 1, "estimated_time": 1.5, "explanation": explanation,
        "solution": solution, "concept": concept, "formula": formula,
        "source_type": "syllabus-derived"
    }
    if answer is not None:
        item["answer"] = answer
    return item

GATE_SOURCE_VARIANTS = [
    _make_source_variant("If a 2x2 matrix has determinant 6 and one eigenvalue is 2, the other eigenvalue is:", "2", "3", "4", "6", "B", "Engineering Mathematics", "Linear Algebra", "Eigenvalues", explanation="For a square matrix, the determinant equals the product of its eigenvalues.", solution="lambda2=det/lambda1=6/2=3.", concept="Eigenvalue product", formula="det(A)=product(lambda_i)"),
    _make_source_variant("The maximum value of f(x)=4x-x^2 for real x is:", "2", "4", "6", "8", "B", "Engineering Mathematics", "Calculus", "Local maxima", explanation="The derivative vanishes at the vertex of the downward parabola.", solution="f'=4-2x=0 gives x=2; f(2)=4.", concept="Quadratic maximum", formula="f'=0"),
    _make_source_variant("The solution of dy/dx=3y with y(0)=2 is:", "2e^x", "3e^(2x)", "2e^(3x)", "3e^(2x)", "C", "Engineering Mathematics", "Ordinary Differential Equations", "First-order ODE", explanation="Separate variables and integrate.", solution="dy/y=3dx, so y=Ce^(3x); C=2.", concept="First-order linear ODE", formula="y=Ce^(3x)"),
    _make_source_variant("For a Poisson random variable with mean 4, its variance is:", "1", "2", "4", "16", "C", "Engineering Mathematics", "Probability and Statistics", "Poisson distribution", explanation="For Poisson distribution, mean and variance are equal.", solution="Variance=lambda=4.", concept="Poisson moments", formula="E(X)=Var(X)=lambda"),
    _make_source_variant("Using the trapezoidal rule with one interval over [0,2], the integral of f(x)=x^2 is estimated as:", "1", "2", "4", "6", "B", "Engineering Mathematics", "Numerical Methods", "Trapezoidal rule", explanation="The single-interval trapezoidal estimate uses endpoint ordinates.", solution="I≈(2/2)[0^2+2^2]=2.", concept="Trapezoidal integration", formula="I≈h/2(f0+f1)"),
    _make_source_variant("At a pin-jointed perfect truss joint with no external load, if only one member is connected at the joint, that member is:", "zero-force", "in compression only", "in tension only", "indeterminate", "A", "Structural Engineering", "Engineering Mechanics", "Zero-force members", explanation="Joint equilibrium cannot be satisfied by a single nonzero member force without an external force.", solution="The member force must be zero.", concept="Joint equilibrium"),
    _make_source_variant("For a simply supported beam of span L carrying a central point load P, the maximum bending moment is:", "PL/8", "PL/4", "PL/2", "PL", "B", "Structural Engineering", "Solid Mechanics", "Beam bending", explanation="The central load produces equal reactions P/2.", solution="Mmax=(P/2)(L/2)=PL/4.", concept="Simply supported beam", formula="Mmax=PL/4"),
    _make_source_variant("The torsional shear stress in a circular shaft varies linearly with radius under elastic torsion. Therefore it is maximum at the:", "centre", "mid-radius", "outer surface", "neutral axis only", "C", "Structural Engineering", "Solid Mechanics", "Uniform torsion", explanation="Shear stress is proportional to radial distance from the shaft axis.", solution="tau=Tr/J, so tau is maximum at r=R.", concept="Torsion", formula="tau=Tr/J"),
    _make_source_variant("For a slender pin-ended column, doubling its effective length changes Euler critical load by a factor of:", "4", "2", "1/2", "1/4", "D", "Structural Engineering", "Solid Mechanics", "Column buckling", explanation="Euler load varies inversely with the square of effective length.", solution="Pcr is proportional to 1/Le^2, so doubling Le gives Pcr/4.", concept="Euler buckling", formula="Pcr=pi^2EI/Le^2"),
    _make_source_variant("In a statically determinate structure, temperature-induced uniform expansion generally produces:", "no stress if expansion is unrestrained", "maximum bending stress", "torsional stress only", "shear failure", "A", "Structural Engineering", "Structural Analysis", "Temperature effects", explanation="A determinate member can undergo compatible free expansion without restraint force.", solution="No restraint means no thermal stress.", concept="Thermal deformation"),
    _make_source_variant("For a prismatic simply supported beam, the point of contraflexure is a point where the bending moment:", "is maximum", "is zero and changes sign", "equals shear force", "is constant", "B", "Structural Engineering", "Structural Analysis", "Bending moment diagram", explanation="Contraflexure is where curvature changes sign, corresponding to a zero bending moment with sign change.", solution="M=0 at the point of contraflexure.", concept="Contraflexure"),
    _make_source_variant("In the slope-deflection method, joint rotations and translations are treated as:", "loads", "unknown displacements", "material properties", "support reactions only", "B", "Structural Engineering", "Structural Analysis", "Slope-deflection", explanation="The displacement method solves for joint displacement degrees of freedom.", solution="Joint rotations/translations are the primary unknowns.", concept="Displacement method"),
    _make_source_variant("For a two-hinged arch subjected to a symmetric vertical loading about its crown, the horizontal thrust is:", "generally zero", "necessarily maximum at crown", "always equal to vertical reaction", "undefined", "B", "Structural Engineering", "Structural Analysis", "Arches", explanation="A two-hinged arch generally develops horizontal thrust even under symmetric vertical loading.", solution="The thrust is not zero in general.", concept="Arch action"),
    _make_source_variant("The shape factor of a rectangular cross-section for plastic bending is:", "1.0", "1.2", "1.5", "2.0", "C", "Structural Engineering", "Steel Structures", "Plastic analysis", explanation="For a rectangular section, Zp/Ze=1.5.", solution="Shape factor=1.5.", concept="Shape factor", formula="Shape factor=Zp/Ze"),
    _make_source_variant("In a singly reinforced RCC beam, increasing the effective depth while keeping reinforcement ratio constant generally increases moment capacity approximately with:", "d", "1/d", "d^2", "sqrt(d)", "C", "Structural Engineering", "Concrete Structures", "Flexural design", explanation="For constant reinforcement ratio, steel area scales with d and lever arm also scales with d.", solution="Mu scales approximately with bd^2.", concept="RCC scaling", formula="Mu≈As fy z"),
    _make_source_variant("The development length of a reinforcing bar is primarily governed by bar diameter, steel stress and:", "aggregate size only", "design bond stress", "cover colour", "water-cement ratio only", "B", "Structural Engineering", "Concrete Structures", "Bond and development length", explanation="Development length is inversely related to design bond stress.", solution="Ld is based on phi, steel stress and bond stress.", concept="Development length", formula="Ld≈phi sigma_s/(4 tau_bd)"),
    _make_source_variant("For a normally consolidated clay, the coefficient of earth pressure at rest is approximately:", "1-sin phi", "1+sin phi", "tan phi", "sin phi", "A", "Geotechnical Engineering", "Soil Mechanics", "Earth pressure", explanation="Jaky's relation gives K0 for normally consolidated soils.", solution="K0=1-sin phi.", concept="At-rest earth pressure", formula="K0=1-sin(phi)"),
    _make_source_variant("If the hydraulic gradient in a soil is doubled while k remains constant, Darcy discharge per unit area becomes:", "half", "unchanged", "double", "four times", "C", "Geotechnical Engineering", "Soil Mechanics", "Permeability", explanation="Darcy flux is proportional to hydraulic gradient.", solution="q=ki, so doubling i doubles q.", concept="Darcy law", formula="q=ki"),
    _make_source_variant("Quick condition in a saturated cohesionless soil is associated with effective stress becoming:", "maximum", "zero", "twice total stress", "negative always", "B", "Geotechnical Engineering", "Soil Mechanics", "Quicksand condition", explanation="At critical upward seepage, seepage force cancels submerged unit weight and effective stress approaches zero.", solution="sigma'=0 at quick condition.", concept="Effective stress"),
    _make_source_variant("For a saturated soil, total stress is 180 kPa and pore pressure is 70 kPa. Effective stress is:", "70 kPa", "110 kPa", "180 kPa", "250 kPa", "B", "Geotechnical Engineering", "Soil Mechanics", "Effective stress", explanation="Terzaghi effective stress equals total stress minus pore pressure.", solution="sigma'=180-70=110 kPa.", concept="Effective stress", formula="sigma'=sigma-u"),
    _make_source_variant("In a standard Proctor compaction test, increasing compactive effort generally shifts the maximum dry density:", "lower with higher optimum water content", "higher with lower optimum water content", "lower with lower optimum water content", "unchanged", "B", "Geotechnical Engineering", "Soil Mechanics", "Compaction", explanation="Higher compactive effort generally increases maximum dry density and reduces optimum moisture content.", solution="The compaction curve shifts upward and typically left.", concept="Compaction effort"),
    _make_source_variant("For a normally consolidated clay, primary consolidation settlement occurs mainly due to:", "increase in grain size", "dissipation of excess pore pressure", "evaporation of water from surface", "cement hydration", "B", "Geotechnical Engineering", "Soil Mechanics", "Consolidation", explanation="Consolidation is volume decrease caused by expulsion of pore water under sustained load.", solution="Excess pore pressure dissipates and effective stress increases.", concept="Primary consolidation"),
    _make_source_variant("A pile derives end-bearing capacity mainly from resistance developed at its:", "head above ground", "shaft only", "tip", "cap beam", "C", "Geotechnical Engineering", "Foundation Engineering", "Pile foundations", explanation="End bearing is the resistance mobilized at the pile tip.", solution="Tip resistance is the end-bearing component.", concept="Pile capacity"),
    _make_source_variant("For steady incompressible flow through a pipe of constant diameter, if elevation is unchanged and losses are negligible, the mean velocity is:", "increased by gravity", "constant", "zero", "dependent only on pressure at one section", "B", "Water Resources Engineering", "Fluid Mechanics", "Continuity", explanation="Continuity requires constant discharge and constant area to give constant mean velocity.", solution="Q=AV and A is constant, hence V is constant.", concept="Continuity", formula="Q=AV"),
    _make_source_variant("The pressure at a point in a static fluid increases with depth because of:", "viscous shear", "weight of fluid above", "surface tension only", "pipe friction", "B", "Water Resources Engineering", "Fluid Mechanics", "Hydrostatics", explanation="Hydrostatic pressure gradient is governed by fluid unit weight.", solution="dp/dz=-gamma.", concept="Hydrostatic pressure", formula="p=gamma h"),
    _make_source_variant("For a pipe flowing full, doubling diameter while keeping discharge constant causes mean velocity to become:", "four times", "twice", "one-half", "one-quarter", "D", "Water Resources Engineering", "Fluid Mechanics", "Pipe flow", explanation="Area is proportional to diameter squared.", solution="V=Q/A and A becomes four times, so V becomes one-quarter.", concept="Continuity", formula="A=pi D^2/4"),
    _make_source_variant("In a rectangular open channel, critical flow occurs when the Froude number is:", "0", "less than 1 only", "equal to 1", "greater than 2", "C", "Water Resources Engineering", "Hydraulics", "Critical flow", explanation="Critical flow is the transition condition with Froude number unity.", solution="Fr=1.", concept="Critical flow", formula="Fr=V/sqrt(gD)"),
    _make_source_variant("A unit hydrograph represents direct runoff resulting from:", "one unit of effective rainfall uniformly distributed over the basin for a specified duration", "one unit of total rainfall at one point", "one hour of evaporation", "one metre of groundwater rise", "A", "Water Resources Engineering", "Hydrology", "Unit hydrograph", explanation="That is the defining linear-system interpretation of a unit hydrograph.", solution="It is basin-specific and duration-specific.", concept="Unit hydrograph"),
    _make_source_variant("If irrigation duty is expressed in hectares per cumec, increasing duty means that the water requirement per hectare is:", "higher", "lower", "unchanged always", "infinite", "B", "Water Resources Engineering", "Irrigation", "Duty and delta", explanation="Higher duty means one unit discharge serves a larger area, so depth requirement is lower for the same base period.", solution="Duty is area irrigated per unit discharge.", concept="Duty"),
    _make_source_variant("In a hydraulic jump in a horizontal channel, the flow changes from:", "subcritical to supercritical", "supercritical to subcritical", "laminar to creeping only", "uniform to hydrostatic only", "B", "Water Resources Engineering", "Hydraulics", "Hydraulic jump", explanation="A hydraulic jump dissipates energy while changing supercritical flow to subcritical flow.", solution="Froude number falls from above 1 to below 1.", concept="Hydraulic jump"),
    _make_source_variant("The main purpose of coagulation in conventional water treatment is to:", "increase dissolved oxygen", "destabilize colloidal particles", "remove all hardness", "sterilize completely", "B", "Environmental Engineering", "Water Treatment", "Coagulation", explanation="Coagulants destabilize colloids so they can agglomerate and settle.", solution="Charge neutralization and floc formation enable removal.", concept="Coagulation"),
    _make_source_variant("The BOD test is primarily an indicator of:", "biodegradable organic pollution", "chloride concentration", "hardness only", "turbidity only", "A", "Environmental Engineering", "Wastewater Treatment", "BOD", explanation="BOD measures oxygen demand associated with biodegradable organic matter under specified test conditions.", solution="Higher BOD generally indicates greater biodegradable organic load.", concept="BOD"),
    _make_source_variant("In activated sludge treatment, the return activated sludge is mainly used to:", "increase grit content", "maintain the desired microorganism concentration in the aeration tank", "raise raw-water turbidity", "remove large debris", "B", "Environmental Engineering", "Wastewater Treatment", "Activated sludge", explanation="Settled biomass is returned to sustain the biological population.", solution="RAS controls biomass concentration in the aeration basin.", concept="Activated sludge"),
    _make_source_variant("A sanitary landfill should primarily provide controlled disposal with measures for:", "leachate and gas management", "increasing open burning", "uncontrolled dumping", "river discharge", "A", "Environmental Engineering", "Solid Waste Management", "Landfill", explanation="Modern landfill design controls leachate, gas and environmental impacts.", solution="Leachate collection and gas management are key controls.", concept="Engineered landfill"),
    _make_source_variant("A cyclone separator is generally more effective for removing:", "very fine dissolved gases", "coarser particulate matter", "dissolved salts", "bacteria from water", "B", "Environmental Engineering", "Air Pollution", "Particulate control", explanation="Cyclones use centrifugal action and are particularly suited to larger particles.", solution="Particle collection efficiency generally improves with particle size.", concept="Cyclone separator"),
    _make_source_variant("Stopping sight distance on a level road consists primarily of lag distance plus:", "overtaking distance", "braking distance", "shoulder width", "median width", "B", "Transportation Engineering", "Highway Engineering", "Sight distance", explanation="SSD includes distance travelled during perception-reaction and braking.", solution="SSD=lag distance+braking distance.", concept="Stopping sight distance"),
    _make_source_variant("For a horizontal highway curve, superelevation is provided mainly to counteract:", "centrifugal effect", "gravity only", "rolling resistance only", "engine torque", "A", "Transportation Engineering", "Highway Engineering", "Superelevation", explanation="Superelevation supplies a component of pavement reaction toward the curve centre.", solution="It reduces reliance on side friction against centrifugal effect.", concept="Superelevation"),
    _make_source_variant("In the fundamental traffic relation q=kv, if density k is fixed and flow q increases, speed v:", "increases proportionally", "decreases proportionally", "becomes zero", "is unrelated to q", "A", "Transportation Engineering", "Traffic Engineering", "Traffic flow", explanation="For fixed density, speed equals flow divided by density.", solution="v=q/k.", concept="Macroscopic traffic flow", formula="q=kv"),
    _make_source_variant("In Webster's signal design method, optimum cycle length is influenced by:", "lost time and critical flow ratios", "only lane width", "only pavement thickness", "only vehicle weight", "A", "Transportation Engineering", "Traffic Engineering", "Signal design", explanation="Webster's method relates optimum cycle length to total lost time and sum of critical flow ratios.", solution="The cycle depends on L and Y.", concept="Webster method", formula="C0=(1.5L+5)/(1-Y)"),
    _make_source_variant("Increasing pavement subgrade strength generally permits a:", "thinner pavement for the same design conditions", "thicker pavement always", "zero pavement", "higher traffic speed only", "A", "Transportation Engineering", "Highway Pavements", "Pavement design", explanation="Stronger subgrade provides greater support to the pavement system.", solution="Required structural thickness generally decreases as support improves.", concept="Pavement support"),
    _make_source_variant("In differential levelling, if the backsight is greater than the foresight, the reduced level of the forward point is generally:", "higher than the previous point", "lower than the previous point", "always equal", "undefined", "A", "Geomatics Engineering", "Surveying", "Levelling", explanation="RL_new=RL_old+BS-FS.", solution="BS>FS gives a positive RL change.", concept="Height of instrument method", formula="RL_new=RL_old+BS-FS"),
    _make_source_variant("The principal function of a total station is to measure:", "only temperature", "angles and electronic distances", "only rainfall", "only soil density", "B", "Geomatics Engineering", "Surveying", "Total station", explanation="A total station integrates electronic angle measurement with EDM.", solution="It measures horizontal/vertical angles and slope distances.", concept="Total station"),
    _make_source_variant("In a traverse, the closing error in coordinates is reduced by an adjustment method such as:", "Bowditch method", "Newton's law", "Manning equation", "Rankine's theory", "A", "Geomatics Engineering", "Surveying", "Traverse adjustment", explanation="Bowditch is a common traverse adjustment method based on proportional distribution.", solution="Corrections are distributed according to line lengths under the usual Bowditch assumptions.", concept="Traverse adjustment"),
    _make_source_variant("The principal cement compound contributing substantially to early strength is:", "C3S", "C2S", "C3A only", "C4AF only", "A", "Construction Materials and Management", "Construction Materials", "Cement chemistry", explanation="Tricalcium silicate hydrates relatively rapidly and contributes strongly to early strength.", solution="C3S is associated with early strength development.", concept="Cement compounds"),
    _make_source_variant("In PERT, the expected activity time using optimistic a, most likely m and pessimistic b is:", "(a+m+b)/3", "(a+4m+b)/6", "(a+2m+b)/4", "(a+b)/2", "B", "Construction Materials and Management", "Project Scheduling", "PERT", explanation="PERT uses a weighted average emphasizing the most likely estimate.", solution="te=(a+4m+b)/6.", concept="PERT expected time", formula="te=(a+4m+b)/6"),
    _make_source_variant("A project activity on the critical path has zero total float under the basic CPM interpretation. Its total float is:", "negative", "zero", "equal to duration", "infinite", "B", "Construction Materials and Management", "Project Scheduling", "CPM", explanation="Critical activities have zero total float in the standard CPM network.", solution="TF=0 on the critical path.", concept="Critical path", formula="TF=LS-ES=LF-EF"),
];


def _difficulty_target(mode):
    return {
        "easy": 2,
        "moderate": 3,
        "hard": 4,
        "very-hard": 5,
        "expert": 6,
        "elite": 7,
    }.get(mode, None)



def _question_fingerprint(question):
    """Stable identity used to prevent excessive repeats between consecutive mocks."""
    source = str(question.get("source_file",""))
    year = str(question.get("source_year",""))
    qnum = str(question.get("source_question",""))
    text = str(question.get("question","")).strip().lower()
    return "|".join((source, year, qnum, text))

def build_gate_mock(mode="mixed", count=60, profile=None, scope="all", avoid_fingerprints=None, attempt_seed=None):
    """
    Build one full-length Civil mock from the uploaded-source-aligned bank.

    Rules:
    - 180 minutes / 100 marks are fixed at the route level.
    - Question count varies by attempt.
    - Exactly five source-backed PYQs are included in every GATE mock.
    - Remaining questions are syllabus-derived originals.
    - Consecutive mocks avoid previous-question fingerprints; at most five can overlap.
    - Questions are shuffled after selection.
    """
    all_questions = (
        GATE_APTITUDE_QUESTIONS
        + GATE_QUESTION_BANK
        + GATE_QUESTION_BANK_EXTRA
        + GATE_PYQ_BANK
        + GATE_SOURCE_VARIANTS
    )
    prepared = []
    seen = set()
    for raw in all_questions:
        q = dict(raw)
        q.setdefault("source_type", "syllabus-derived")
        fp = _question_fingerprint(q)
        if fp in seen:
            continue
        seen.add(fp)
        q["_fingerprint"] = fp
        q["section"] = (
            "General Aptitude" if q.get("subject") == "General Aptitude"
            else "Engineering Mathematics" if q.get("subject") == "Engineering Mathematics"
            else "Civil Core"
        )
        prepared.append(q)

    if scope != "all":
        prepared = [
            q for q in prepared
            if (
                scope == "mathematics" and q["subject"] == "Engineering Mathematics"
            ) or (
                scope == "aptitude" and q["subject"] == "General Aptitude"
            ) or (
                scope == "core" and q["section"] == "Civil Core"
            )
        ]

    rng = random.Random(attempt_seed if attempt_seed is not None else secrets.randbits(64))
    previous = set(avoid_fingerprints or [])

    pyqs = [q for q in prepared if q.get("source_type") == "pyq" or q.get("source_file")]
    originals = [q for q in prepared if not (q.get("source_type") == "pyq" or q.get("source_file"))]

    rng.shuffle(pyqs)
    rng.shuffle(originals)

    # Prefer zero overlap with the immediately preceding test. The fallback
    # permits at most five repeats when the available source pool requires it.
    fresh_pyqs = [q for q in pyqs if q["_fingerprint"] not in previous]
    old_pyqs = [q for q in pyqs if q["_fingerprint"] in previous]
    pyq_target = min(5, len(pyqs), count)
    selected = fresh_pyqs[:pyq_target]
    if len(selected) < pyq_target:
        selected.extend(old_pyqs[:pyq_target-len(selected)])

    selected_fps = {q["_fingerprint"] for q in selected}
    max_previous_overlap = 5

    fresh_originals = [q for q in originals if q["_fingerprint"] not in previous]
    old_originals = [q for q in originals if q["_fingerprint"] in previous and q["_fingerprint"] not in selected_fps]

    needed = max(0, count - len(selected))
    selected.extend(fresh_originals[:needed])

    if len(selected) < count:
        # Only use previous-test questions after exhausting fresh questions,
        # and never exceed five overlaps in total.
        overlap_slots = max(0, max_previous_overlap - sum(
            1 for q in selected if q["_fingerprint"] in previous
        ))
        selected.extend(old_originals[:min(overlap_slots, count-len(selected))])

    if len(selected) < count:
        # This is a hard safety fallback for future bank changes. It is only
        # reached when the bank itself is too small for the requested count.
        remaining = [q for q in prepared if q["_fingerprint"] not in selected_fps]
        rng.shuffle(remaining)
        selected.extend(remaining[:count-len(selected)])

    selected = selected[:count]

    # Fixed 100-mark paper with variable question count. For N questions:
    # one_mark = 2N-100 and two_mark = 100-N.
    marks = allocate_question_marks(count, 100)
    rng.shuffle(selected)
    one_mark = marks["one_mark"]
    for i, q in enumerate(selected):
        q["marks"] = 1 if i < one_mark else 2
        q.pop("_fingerprint", None)

    return selected

def next_difficulty_mode(score_percent, current_mode="mixed"):
    if score_percent > 85:
        return {"mixed": "hard", "easy": "moderate", "moderate": "hard", "hard": "very-hard", "very-hard": "expert", "expert": "elite", "elite": "elite"}.get(current_mode, "hard")
    if score_percent < 40:
        return {"mixed": "easy", "easy": "easy", "moderate": "easy", "hard": "moderate", "very-hard": "hard", "expert": "very-hard", "elite": "expert"}.get(current_mode, "easy")
    return current_mode


def distribution(questions):
    return Counter(question["difficulty_level"] for question in questions)


def scaled_difficulty_distribution(question_count):
    """Scale the mandated 20-question mix using largest-remainder rounding."""
    ratios = {"L1": 1, "L2": 2, "L3": 5, "L4": 5, "L5": 4, "L6": 2, "L7": 1}
    exact = {level: question_count * value / 20 for level, value in ratios.items()}
    result = {level: int(value) for level, value in exact.items()}
    remaining = question_count - sum(result.values())
    for level, _ in sorted(exact.items(), key=lambda item: item[1] - int(item[1]), reverse=True)[:remaining]:
        result[level] += 1
    return result
