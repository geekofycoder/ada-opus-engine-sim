"""The complaint categories, covering ~80% of outpatient presentations.

Built from the acute/chronic table. Two things to understand:

1. A category is what the PATIENT SAYS, not what they turn out to have.
   "Dyslipidemia" is not a category - nobody walks in complaining of it.
   It is found on a blood test. So it lives under `asymptomatic_screening`.

2. `kind` decides what happens next:

     differential  -> load/generate a rulebook, run the question loop
     route         -> no rulebook, no questions. Hand off and stop.

   Routing a screening visit into a symptom-narrowing engine would produce
   confident nonsense, so we don't.

`sex_specific` controls the cache key. Most complaints present the same way
in both sexes, so one rulebook serves everyone and we halve the number of
rulebooks we ever have to generate.
"""

DIFFERENTIAL = "differential"
ROUTE = "route"

CATEGORIES = {
    # ---------------------------------------------------------- ACUTE
    "respiratory_urti": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Respiratory / cough / cold / sore throat",
        covers="URTI, bronchitis, pharyngitis, sinusitis, flu, pneumonia, asthma",
        patient_says="cough, blocked nose, sore throat, breathless, chest congestion"),

    "fever": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Fever",
        covers="viral fever, dengue, typhoid, malaria, UTI-related fever, abscess",
        patient_says="fever, chills, body ache, feeling hot, shivering"),

    "acute_gi": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Acute gastrointestinal",
        covers="gastroenteritis, food poisoning, viral diarrhoea, dysentery",
        patient_says="loose motions, vomiting, stomach upset, diarrhoea"),

    "acid_peptic_gerd": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Acid-peptic / reflux",
        covers="GERD, gastritis, peptic ulcer, functional dyspepsia",
        patient_says="heartburn, acidity, burning in chest or upper stomach, sour burps"),

    "skin_allergy": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Skin and allergy",
        covers="urticaria, eczema, contact dermatitis, fungal infection, drug rash",
        patient_says="rash, itching, hives, skin patches, swelling"),

    "urinary": dict(
        kind=DIFFERENTIAL, sex_specific=True,     # UTI differs sharply by sex
        label="Urinary symptoms",
        covers="cystitis, pyelonephritis, urethritis, stones, prostatitis",
        patient_says="burning urination, going often, blood in urine, urgency"),

    # -------------------------------------------------------- CHRONIC
    "musculoskeletal_pain": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Musculoskeletal / back / joint pain",
        covers="mechanical low back pain, osteoarthritis, RA, sciatica, "
               "frozen shoulder, gout, fibromyalgia",
        patient_says="back pain, joint pain, knee pain, stiffness, neck pain"),

    "fatigue_weakness": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Fatigue / weakness",
        covers="iron-deficiency anaemia, B12/D deficiency, hypothyroidism, "
               "diabetes, depression, chronic infection",
        patient_says="always tired, no energy, weakness, exhausted"),

    "thyroid_symptoms": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Thyroid-type symptoms",
        covers="hypothyroidism, hyperthyroidism, goitre, thyroiditis",
        patient_says="weight gain or loss, feeling cold or hot, hair fall, "
                     "neck swelling, palpitations"),

    "diabetes_symptoms": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Diabetes-type symptoms",
        covers="new T2DM, uncontrolled diabetes, prediabetes, diabetes "
               "complications",
        patient_says="very thirsty, passing urine a lot, blurred vision, "
                     "losing weight, slow-healing wounds"),

    "headache": dict(
        kind=DIFFERENTIAL, sex_specific=False,
        label="Headache",
        covers="tension headache, migraine, sinusitis, hypertension-related, "
               "cluster, raised ICP",
        patient_says="headache, head pain, migraine, pressure in head"),

    "dizziness": dict(
        kind=DIFFERENTIAL, sex_specific=True,
        label="Dizziness / giddiness",
        covers="BPPV, orthostatic hypotension, anaemia, vestibular neuritis, "
               "arrhythmia, Meniere's",
        patient_says="dizzy, giddy, room spinning, feel faint, lightheaded"),

    # ------------------------------------------------------- NOT A DIFFERENTIAL
    "chronic_followup": dict(
        kind=ROUTE, sex_specific=False,
        label="Follow-up for a known condition",
        covers="known hypertension, known diabetes, known thyroid, known "
               "dyslipidemia - review and monitoring, not diagnosis",
        patient_says="here for my BP check, sugar review, routine follow-up, "
                     "medicine refill",
        route_message=(
            "This is a follow-up for a condition you already have, not a new "
            "problem to work out. You need your readings and bloods reviewed, "
            "not a list of questions. Please see your clinician with your "
            "latest results and current medicines.")),

    "asymptomatic_screening": dict(
        kind=ROUTE, sex_specific=False,
        label="Screening with no symptoms",
        covers="dyslipidemia, hypertension found on a BP check, prediabetes - "
               "these are almost always SILENT and found on testing",
        patient_says="no symptoms, just want a health check, master health "
                     "checkup, insurance medical",
        route_message=(
            "Conditions like high cholesterol and early high blood pressure "
            "usually cause no symptoms at all, so questions cannot find them. "
            "They are picked up by a blood test and a BP reading. Please book "
            "a basic health check.")),

    "unclear": dict(
        kind=ROUTE, sex_specific=False,
        label="Could not be classified",
        covers="nothing - this is the fallback when the complaint is too vague "
               "or sits outside the covered categories",
        patient_says="",
        route_message=(
            "Sorry, I could not work out which area this falls under. "
            "Try describing the main symptom, where it is, and how long you "
            "have had it. Or see a clinician directly.")),
}


def is_differential(cat):
    return CATEGORIES.get(cat, {}).get("kind") == DIFFERENTIAL


def sex_specific(cat):
    return CATEGORIES.get(cat, {}).get("sex_specific", True)


def route_message(cat):
    return CATEGORIES.get(cat, {}).get("route_message", "")


def ids():
    return list(CATEGORIES)


def prompt_block():
    """The category list as Claude sees it when classifying."""
    out = []
    for cid, m in CATEGORIES.items():
        out.append(f"{cid}\n    is: {m['label']}\n"
                   f"    covers: {m['covers']}\n"
                   f"    patient might say: {m['patient_says'] or '(fallback only)'}")
    return "\n\n".join(out)
