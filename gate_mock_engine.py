"""Original, syllabus-bounded GATE Civil mock-test generation data."""

from collections import Counter

from gate_question_bank_extra import GATE_QUESTION_BANK_EXTRA


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

GATE_SYLLABI = {"2025": GATE_SYLLABUS_2025, "2026": GATE_SYLLABUS_2026, "2027": GATE_SYLLABUS_2027}
GATE_SYLLABUS = GATE_SYLLABUS_2026


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


def _difficulty_target(mode):
    return {
        "easy": 2,
        "moderate": 3,
        "hard": 4,
        "very-hard": 5,
        "expert": 6,
        "elite": 7,
    }.get(mode, None)


def build_gate_mock(mode="mixed", count=20, profile=None, scope="all"):
    """Return a syllabus-tagged selection for a difficulty, profile, and scope."""
    questions = GATE_APTITUDE_QUESTIONS + GATE_QUESTION_BANK + GATE_QUESTION_BANK_EXTRA
    questions = [
        question for question in questions
        if scope == "all"
        or (scope == "mathematics" and question["subject"] == "Engineering Mathematics")
        or (scope == "core" and question["subject"] not in ("Engineering Mathematics", "General Aptitude"))
        or (scope == "aptitude" and question["subject"] == "General Aptitude")
    ]
    if profile in GATE_MOCK_PROFILES:
        settings = gate_mock_structure(profile)
        count = settings["total_questions"]
        quotas = {
            "General Aptitude": settings["aptitude_questions"],
            "Engineering Mathematics": settings["math_questions"],
            "Civil Core": settings["core_questions"],
        }
        selected = []
        for section_name, quota in quotas.items():
            section_questions = [
                question for question in questions
                if (section_name == "General Aptitude" and question["subject"] == section_name)
                or (section_name == "Engineering Mathematics" and question["subject"] == section_name)
                or (section_name == "Civil Core" and question["subject"] not in ("General Aptitude", "Engineering Mathematics"))
            ]
            if mode == "mixed" or not _difficulty_target(mode):
                section_selected = section_questions[:quota]
            else:
                target = _difficulty_target(mode)
                section_selected = sorted(section_questions, key=lambda item: (abs(item["difficulty_rating"] - target), item["difficulty_rating"]))[:quota]
            if len(section_selected) < quota and section_questions:
                section_selected.extend(section_questions[index % len(section_questions)] for index in range(quota - len(section_selected)))
            selected.extend(section_selected)
    elif mode == "mixed" or not _difficulty_target(mode):
        selected = questions[:count]
    else:
        target = _difficulty_target(mode)
        selected = sorted(questions, key=lambda item: (abs(item["difficulty_rating"] - target), item["difficulty_rating"]))[:count]
    if len(selected) < count and questions:
        # The allocator supports the requested profile while the bank is being expanded.
        selected.extend(questions[index % len(questions)] for index in range(count - len(selected)))
    result = [dict(question) for question in selected]
    for question in result:
        question["section"] = (
            "General Aptitude" if question["subject"] == "General Aptitude"
            else "Engineering Mathematics" if question["subject"] == "Engineering Mathematics"
            else "Civil Core"
        )
    if profile in GATE_MOCK_PROFILES:
        # 100-mark GATE CE distribution:
        # GA = 5x1 + 5x2 = 15
        # Mathematics = 1x1 + 6x2 = 13
        # Civil Core = 24x1 + 24x2 = 72
        one_mark_limits = {
            "General Aptitude": 5,
            "Engineering Mathematics": 1,
            "Civil Core": 24,
        }
        seen = {
            "General Aptitude": 0,
            "Engineering Mathematics": 0,
            "Civil Core": 0,
        }
        for question in result:
            section = question["section"]
            seen[section] += 1
            question["marks"] = (
                1 if seen[section] <= one_mark_limits[section] else 2
            )
    return result


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
