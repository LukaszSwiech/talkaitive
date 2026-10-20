"""The golden set of the AI eval: one data shape for every series, and its cases.

The scorer (`scoring.py`), its tests and the eval script read these types. Message
numbers count only the learner's messages, from 1, as in the analysis transcript
(`conversations/llm.py`, `_build_transcript`): every history entry whose role is
not `"assistant"` is a learner message.

Data source and licence
-----------------------

The learner messages are sentences from the MERLIN Written Learner Corpus for
Czech, German, Italian 1.1 (Wisniewski et al., Eurac Research),
http://hdl.handle.net/20.500.12124/6, CC BY-SA 4.0: German texts whose overall CEFR
rating is B1 or B2. Each `source` is the MERLIN Author ID of the text a sentence
comes from.

Adaptation:

- Learner sentences are quoted verbatim, with their mistakes (and their spacing).
  Several sentences, from one or several texts of the same task, are put into one
  short chat; the partner messages around them are written for this eval in
  correct B1-B2 German, except the planted partner mistakes in `PARTNER_PLANTS`.
- Correct forms come from MERLIN's target hypothesis 1 (the minimal correction by
  the corpus annotators), never from a model. Every difference between a learner
  sentence and its target hypothesis is classified: a mistake with one clear
  textbook rule is a `GoldMistake` (its category follows that rule and `rule` names
  it; a second category only when the rule itself is borderline, e.g. a verb's
  fixed preposition); spelling, capitalisation and compound spelling that keep the
  meaning are a `Typo`; any other difference is `Neutral`. Two kinds of difference
  are dropped: a lower-case first word that only follows from the letter's
  salutation ("Liebe X, ich ...") and punctuation-only changes (no word to anchor;
  the analysis prompt tells the model to ignore punctuation).
- Scene notes of `MEMORY_CASES` and every partner message are written for this
  eval; they contain no corpus text.

This file, as an adaptation of MERLIN, is shared under CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0/).
"""

from dataclasses import dataclass

# One history entry: (role, text), role "user" for the learner, "assistant" for
# the partner, oldest first (as `llm.generate_turn` and `llm.analyze_mistakes`).
History = tuple[tuple[str, str], ...]

GRAMMAR = "grammar"
VOCABULARY = "vocabulary"
WORD_ORDER = "word_order"
CATEGORIES = frozenset({GRAMMAR, VOCABULARY, WORD_ORDER})


@dataclass(frozen=True)
class GoldMistake:
    """A known mistake in one learner message.

    `wrong_key` / `correct_key` are the shortest keywords of the mistake and of its
    correction; `categories` allows 1-2 categories for borderline cases; `source`
    is the id of the corpus text.
    """

    message: int
    wrong_key: str
    correct_key: str
    categories: frozenset[str]
    rule: str
    source: str


@dataclass(frozen=True)
class Typo:
    """Spelling, capitalisation or compound spelling the analysis must not report."""

    message: int
    token: str
    source: str


@dataclass(frozen=True)
class Neutral:
    """An ambiguous correction (e.g. `dass` / `das`): neither a hit nor an extra."""

    message: int
    token: str
    source: str


@dataclass(frozen=True)
class AnalysisCase:
    """A short conversation for the post-conversation analysis.

    `partner_questions` holds one group of keywords per question the partner
    asked; a group is found when any of its keywords occurs in a scene note.
    """

    id: str
    history: History
    mistakes: tuple[GoldMistake, ...]
    typos: tuple[Typo, ...]
    neutrals: tuple[Neutral, ...]
    correct_messages: tuple[int, ...]
    partner_questions: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class TurnCase:
    """An agent turn; the last history message is the learner's, with one mistake.

    `wrong_forms[0]` is the learner's own wrong form; the others are the same
    mistake echoed by the partner (e.g. in the second person). A reply that contains
    any of them repeats the mistake.
    """

    id: str
    topic_key: str
    history: History
    wrong_forms: tuple[str, ...]
    correct_forms: tuple[str, ...]
    category: str
    rule: str
    source: str


@dataclass(frozen=True)
class MemoryCase:
    """An opening turn with scene notes of questions that were already asked.

    `forbidden` holds one group of German keywords per such question; a group is
    hit when any of its keywords occurs in the reply.
    """

    id: str
    topic_key: str
    scene_notes: tuple[tuple[str, ...], ...]
    forbidden: tuple[tuple[str, ...], ...]


def _partner(text: str) -> tuple[str, str]:
    return ("assistant", text)


def _learner(text: str) -> tuple[str, str]:
    return ("user", text)


def _gold(
    message: int,
    wrong_key: str,
    correct_key: str,
    rule: str,
    source: str,
    *categories: str,
) -> GoldMistake:
    return GoldMistake(
        message, wrong_key, correct_key, frozenset(categories), rule, source
    )


# --- analysis: short chats, learner messages from MERLIN -------------------------

ANALYSIS_CASES: tuple[AnalysisCase, ...] = (
    AnalysisCase(
        id="silvester-familie",
        history=(
            _partner("Hallo! Schön, dass du da bist. Wie hast du Silvester gefeiert?"),
            _learner(
                "Die Silvesternacht habe ich mit meinem Mann und meine Familie verbracht."
            ),
            _partner("Das klingt gemütlich. Bei uns war es ganz ruhig."),
            _learner("Wir auch haben gemeinsam gekocht und gegessen."),
            _partner("Lecker! Habt ihr auch Gäste eingeladen?"),
            # Correct in MERLIN 1061_0120481.
            _learner(
                "Wir haben viele Freunde eingeladen und eine schöne Party gemacht."
            ),
            _partner("Super, das freut mich."),
            _learner("Meine Silvesternacht war sehr gut auch."),
            _learner("Ich wünshe dir alles gute zum neuen Jahr."),
        ),
        mistakes=(
            _gold(
                1,
                "meine Familie",
                "meiner Familie",
                "Dativ nach mit: meiner Familie",
                "1061_0120438",
                GRAMMAR,
            ),
            _gold(
                2,
                "auch haben",
                "haben auch",
                "Verbzweitstellung im Aussagesatz",
                "1061_0120432",
                WORD_ORDER,
            ),
            _gold(
                4,
                "gut auch",
                "auch sehr gut",
                "auch steht vor dem Satzteil, auf den es sich bezieht",
                "1061_0120499",
                WORD_ORDER,
            ),
        ),
        typos=(Typo(5, "wünshe", "1061_0120450"), Typo(5, "gute", "1061_0120450")),
        neutrals=(),
        correct_messages=(3,),
        partner_questions=(("Silvester", "New Year"), ("Gäste", "guests")),
    ),
    AnalysisCase(
        id="arbeit-pflegerin",
        history=(
            _partner("Hey, lange nicht gesehen! Was machst du gerade beruflich?"),
            _learner("Zurzeit ich arbeite, leider, als Pflegerin."),
            _partner("Warum leider? Ich dachte, die Arbeit gefällt dir."),
            _learner("Ich arbeite sehr viele und nicht das, was ich will."),
            # Planted: "seit drei Jahre" (correct: "seit drei Jahren").
            _partner(
                "Das verstehe ich gut. Ich arbeite seit drei Jahre in einem "
                "Krankenhaus, das ist auch anstrengend."
            ),
            # Correct in MERLIN 1061_0120438.
            _learner("Meine Kollegen sind sehr nett."),
            _partner("Das ist wichtig. Mein Chef sagt immer, man muss flexibel sein."),
            _learner("Ich bin sehr Flexibel und Mobilität."),
            _learner("Arbeit ist immer schwer und wir haben eine neue kolleagin."),
        ),
        mistakes=(
            _gold(
                1,
                "ich arbeite",
                "arbeite ich",
                "Verbzweitstellung: nach zurzeit das Verb vor dem Subjekt",
                "1061_0120459",
                WORD_ORDER,
            ),
            _gold(
                2,
                "viele",
                "viel",
                "viel als Adverb wird nicht dekliniert",
                "1061_0120459",
                GRAMMAR,
            ),
            _gold(
                4,
                "Mobilität",
                "mobil",
                "Wortart: Adjektiv mobil statt Nomen Mobilität",
                "1023_0101894",
                VOCABULARY,
            ),
        ),
        typos=(
            Typo(4, "Flexibel", "1023_0101894"),
            Typo(5, "kolleagin", "1061_0120881"),
        ),
        neutrals=(),
        correct_messages=(3,),
        partner_questions=(("beruflich", "job"), ("warum", "why")),
    ),
    AnalysisCase(
        id="hund-koeln",
        history=(
            _partner("Hallo! Du siehst ein bisschen gestresst aus."),
            _learner(
                "Morgen muss ich nach Köln hinfahren und ich kann nicht mein "
                "Haustier mitnehmen."
            ),
            _partner("Oh je. Wie lange bleibst du denn in Köln?"),
            _learner("Ich weiß nicht genau, wie lange muss ich in Köln bleiben."),
            # Planted: "auf ihm" (correct: "auf ihn").
            _partner("Kein Problem, ich passe gerne auf ihm auf."),
            # Correct in MERLIN 1091_0000245.
            _learner("Ich habe einen Hund, er heißt Waldi."),
            _partner("Waldi ist so süß! Was frisst er denn am liebsten?"),
            _learner("Du sollst ihn nur sein Abendessen geben."),
            _partner("Alles klar, das ist einfach."),
            _learner("Ich habe das Essen für meinen Hund schon vorberaitet."),
            _learner(
                "Wenn du meinen Hund bei dir bleiben möchtest, ruf mich bitte "
                "sofort  auf meinem Handy an."
            ),
        ),
        mistakes=(
            _gold(
                1,
                "nicht mein",
                "Haustier nicht",
                "nicht steht vor dem Infinitiv am Satzende, nach dem Objekt",
                "1091_0000244",
                WORD_ORDER,
            ),
            _gold(
                2,
                "muss ich",
                "bleiben muss",
                "Verbendstellung im indirekten Fragesatz",
                "1091_0000167",
                WORD_ORDER,
            ),
            _gold(
                4,
                "ihn",
                "ihm",
                "Dativ für die Person bei geben",
                "1091_0000244",
                GRAMMAR,
            ),
            _gold(
                6,
                "bleiben",
                "haben",
                "Wortwahl: jemanden bei sich haben",
                "1091_0000155",
                VOCABULARY,
            ),
        ),
        typos=(Typo(5, "vorberaitet", "1091_0000167"),),
        neutrals=(),
        correct_messages=(3,),
        partner_questions=(("wie lange", "how long"), ("frisst", "eat", "food")),
    ),
    AnalysisCase(
        id="katze-reise",
        history=(
            _partner("Hallo! Ich habe deine Nachricht bekommen. Wohin fährst du denn?"),
            _learner("Ich bin nicht zu Hause für zwei Wochen."),
            _partner("Zwei Wochen sind lang!"),
            _learner("Wie du schon weist, ich habe eine Katze."),
            _partner("Ja, natürlich. Wie heißt sie noch mal?"),
            _learner("Kannst du bitte mit meine Katze spielen."),
            _partner("Klar, gern. Ich spiele sehr gern mit Katzen."),
            # Correct in MERLIN 1091_0000234.
            _learner("In diesem Hotel sind Haustiere nicht erlaubt."),
            _partner("Dann passe ich natürlich auf sie auf."),
            _learner("Ich bin sehr bedanken für dein Mithilfe."),
        ),
        mistakes=(
            _gold(
                1,
                "Hause für",
                "Wochen nicht",
                "Zeitangabe vor nicht; nicht direkt vor der Ortsergänzung",
                "1091_0000234",
                WORD_ORDER,
            ),
            _gold(
                2,
                "ich habe",
                "habe ich",
                "Verbzweitstellung nach vorangestelltem Nebensatz",
                "1091_0000168",
                WORD_ORDER,
            ),
            _gold(
                3,
                "meine Katze",
                "meiner Katze",
                "Dativ nach mit: meiner Katze",
                "1091_0000242",
                GRAMMAR,
            ),
            _gold(
                5,
                "bedanken",
                "dankbar",
                "Wortwahl: dankbar sein statt sich bedanken",
                "1091_0000158",
                VOCABULARY,
            ),
            _gold(
                5,
                "dein Mithilfe",
                "deine Mithilfe",
                "Genus: die Mithilfe, also deine",
                "1091_0000158",
                GRAMMAR,
            ),
        ),
        typos=(Typo(2, "weist", "1091_0000168"),),
        neutrals=(),
        correct_messages=(4,),
        partner_questions=(("wohin", "where"), ("heißt", "name")),
    ),
    AnalysisCase(
        id="wohnung-neuburg",
        history=(
            _partner("Hallo! Ich habe gehört, du ziehst bald um."),
            # Correct in MERLIN 1071_0024799.
            _learner("Ich habe endlich eine neue Arbeit in Neuburg gefunden."),
            _partner("Glückwunsch! Wann fängt die neue Arbeit an?"),
            _learner("Deshalb ich muss eine Wohnung suchen."),
            _partner("In Neuburg sind die Wohnungen leider ziemlich teuer."),
            _learner("Ich suche eine Wohnung in Neuburg, kannst du mir bitte hilfe?"),
            _partner("Natürlich helfe ich dir. Wie viele Zimmer brauchst du?"),
            _learner("Wenn die Wohnung Erdgeschoss ist, ich bin sehr zufrieden."),
            _partner("Ich kenne einen Makler in Neuburg."),
            _learner("Vieleicht kannst du mir helfen?"),
        ),
        mistakes=(
            _gold(
                2,
                "ich muss",
                "muss ich",
                "Verbzweitstellung nach deshalb",
                "1091_0000207",
                WORD_ORDER,
            ),
            _gold(
                3,
                "hilfe",
                "helfen",
                "Wortart: Verb helfen statt Nomen Hilfe",
                "1071_0024757",
                VOCABULARY,
            ),
            _gold(
                4,
                "Erdgeschoss",
                "im Erdgeschoss",
                "Ortsangabe mit Präposition: im Erdgeschoss",
                "1091_0000075",
                GRAMMAR,
            ),
            _gold(
                4,
                "ich bin",
                "bin ich",
                "Verbzweitstellung nach vorangestelltem Nebensatz",
                "1091_0000075",
                WORD_ORDER,
            ),
        ),
        typos=(Typo(5, "Vieleicht", "1071_0024799"),),
        neutrals=(),
        correct_messages=(1,),
        partner_questions=(("fängt", "start", "begin"), ("Zimmer", "rooms")),
    ),
    AnalysisCase(
        id="baby-glueckwunsch",
        history=(
            _partner("Hallo! Stell dir vor: Wir haben eine Tochter bekommen!"),
            # Correct in MERLIN 1071_0024866.
            _learner("Oh, das ist SUPER, wunderbar, toll!"),
            _learner("ich frohe mich für euch."),
            # Planted: "in die Nacht" (correct: "in der Nacht").
            _partner(
                "Danke! Wir sind sehr glücklich, aber auch müde, weil das Baby in "
                "die Nacht oft weint."
            ),
            _learner("Wie es der Mutter des Babys geht?"),
            _partner(
                "Ihr geht es schon viel besser, danke. Willst du uns bald besuchen?"
            ),
            _learner("Ich hoffe, dass ich nächste Woche es kennenlernen kann."),
            _partner("Gern, komm einfach vorbei. Hast du eigentlich selbst Kinder?"),
            _learner("Ich gratuliere und wünsche viel Glük, Gesund und alles Gute."),
        ),
        mistakes=(
            _gold(
                2,
                "frohe",
                "freue",
                "Wortwahl: sich freuen (Verb); froh ist ein Adjektiv",
                "1071_0024881",
                VOCABULARY,
            ),
            _gold(
                3,
                "Wie es",
                "Wie geht",
                "Verbzweitstellung in der W-Frage",
                "1071_0024865",
                WORD_ORDER,
            ),
            _gold(
                4,
                "Woche es",
                "es nächste Woche",
                "unbetontes Pronomen vor der Zeitangabe im Mittelfeld",
                "1071_0024834",
                WORD_ORDER,
            ),
            _gold(
                5,
                "Gesund",
                "Gesundheit",
                "Wortart: Nomen Gesundheit statt Adjektiv gesund",
                "1071_0024881",
                VOCABULARY,
            ),
        ),
        typos=(Typo(5, "Glük", "1071_0024881"),),
        neutrals=(),
        correct_messages=(1,),
        partner_questions=(("besuchen", "visit"), ("Kinder", "children", "kids")),
    ),
    AnalysisCase(
        id="fahrkarte-ausflug",
        history=(
            _partner("Hi! Schön, dass du anrufst."),
            _learner(
                "Ich habe eine Fahrkarte für einen Busausflug nach Stadt X gekauft, "
                "aber kann nicht leider fahren."
            ),
            _partner("Schade! Warum kannst du nicht fahren?"),
            # Correct in MERLIN 1091_0000252.
            _learner("Mein Großvater ist krank und liegt im Krankenhaus."),
            _partner("Das tut mir leid. Ich hoffe, es geht ihm bald besser."),
            _learner("Ich möchte wissen, ob du die Fahrkarte haben möchte."),
            _partner("Sehr gern! Wann fährt der Bus denn los?"),
            _learner(
                "Die ganze Reise ist kostenlos und du kann am Abend zurückkommen."
            ),
            _partner("Super, das ist ja praktisch."),
            _learner("Ich denke du hast frei am Wockenende."),
        ),
        mistakes=(
            _gold(
                1,
                "nicht leider",
                "leider nicht",
                "Satzadverb leider steht vor nicht",
                "1091_0000114",
                WORD_ORDER,
            ),
            _gold(
                3,
                "haben möchte",
                "möchtest",
                "Konjugation, 2. Person Singular: du möchtest",
                "1091_0000260",
                GRAMMAR,
            ),
            _gold(
                4,
                "du kann",
                "du kannst",
                "Konjugation, 2. Person Singular: du kannst",
                "1091_0000260",
                GRAMMAR,
            ),
        ),
        typos=(Typo(5, "Wockenende", "1091_0000247"),),
        neutrals=(),
        correct_messages=(2,),
        partner_questions=(("warum", "why"), ("wann", "when")),
    ),
    AnalysisCase(
        id="besuch-sommer",
        history=(
            _partner("Hallo! Wie schön, von dir zu hören."),
            _learner("Ich habe schon dich lange nicht gesehen."),
            _partner("Stimmt, das ist wirklich lange her. Wann hast du Urlaub?"),
            _learner("Sobald ich Uhrlaub bekomme, komme ich zu dir."),
            _partner("Oder ich besuche zuerst dich, ich habe im Mai frei."),
            _learner("Ich würde mich sehr frohen, wenn du mich besuchst!"),
            _partner("Super! Wo kann ich bei dir schlafen?"),
            _learner("Hier haben wir ein leere Zimmer und du kannst hier schlafen."),
            _partner("Perfekt. Ich möchte auch gern einmal ans Meer."),
            # Correct in MERLIN 1061_0120880.
            _learner("Wenn du mich besuchst, können wir vielleicht zusammen fahren."),
        ),
        mistakes=(
            _gold(
                1,
                "schon dich",
                "dich schon",
                "unbetontes Pronomen vor dem Adverb im Mittelfeld",
                "1061_0120456",
                WORD_ORDER,
            ),
            _gold(
                3,
                "frohen",
                "freuen",
                "Wortwahl: sich freuen (Verb); froh ist ein Adjektiv",
                "1061_0120882",
                VOCABULARY,
            ),
            _gold(
                4,
                "ein leere",
                "ein leeres",
                "Adjektivendung nach ein, Neutrum Akkusativ: -es",
                "1061_0120484",
                GRAMMAR,
            ),
        ),
        typos=(Typo(2, "Uhrlaub", "1061_0120311"),),
        neutrals=(),
        correct_messages=(5,),
        partner_questions=(("Urlaub", "holiday", "vacation"), ("schlafen", "sleep")),
    ),
    AnalysisCase(
        id="geburtstag-party",
        history=(
            _partner("Hallo! Lena hat erzählt, dass du bald Geburtstag hast."),
            # Correct in MERLIN 1061_0120327.
            _learner("Ja, ich habe bald Geburtstag."),
            _partner("Wie willst du feiern?"),
            _learner("Am Wochenende habe ich eine klein Geburtstag Party."),
            _partner("Schön! Ich bringe gern einen Kuchen mit."),
            _learner("Wir treffen uns zu meine Party."),
            _partner("Und was wünschst du dir zum Geburtstag?"),
            # Correct in MERLIN 1061_0120327.
            _learner("Ich hätte gern einen Hund oder eine Katze."),
            _partner(
                "Ein Haustier ist ein großes Geschenk. Ich muss erst mit Lena sprechen."
            ),
            _learner("Ich warte für deine Antwort."),
        ),
        mistakes=(
            _gold(
                2,
                "eine klein",
                "eine kleine",
                "Adjektivendung nach eine: kleine",
                "1061_0120857",
                GRAMMAR,
            ),
            _gold(
                3,
                "meine Party",
                "meiner Party",
                "Dativ nach zu: zu meiner Party",
                "1061_0120350",
                GRAMMAR,
            ),
            _gold(
                5,
                "für deine",
                "auf deine",
                "feste Präposition des Verbs: warten auf",
                "1061_0120351",
                VOCABULARY,
                GRAMMAR,
            ),
        ),
        typos=(Typo(2, "Geburtstag Party", "1061_0120857"),),
        neutrals=(),
        correct_messages=(1, 4),
        partner_questions=(
            ("feiern", "celebrate"),
            ("wünschst", "wish", "present", "gift"),
        ),
    ),
    AnalysisCase(
        id="schwimmbad",
        history=(
            _partner("Hallo! Was machst du am Wochenende?"),
            # Correct in MERLIN 1071_0248307.
            _learner("ich will am Samstag um 18 Uhr ins Schwimmbad gehen."),
            _learner("Mochtest du mit mir Schwimmen gehen?"),
            _partner("Ja, sehr gern! Was soll ich mitbringen?"),
            _learner("Konntest du Getränken mitbringen?"),
            # Correct in MERLIN 1071_0248309.
            _learner("Wir bringen Pizza und Obst mit."),
            _partner("Gut, ich frage noch meinen Bruder, ob er auch mitkommt."),
            _learner("Ich warte deine Antwort."),
        ),
        mistakes=(
            _gold(
                3,
                "Getränken",
                "Getränke",
                "Akkusativ Plural ohne -n: Getränke",
                "1071_0248309",
                GRAMMAR,
            ),
            _gold(
                5,
                "warte deine",
                "auf deine",
                "feste Präposition des Verbs: warten auf",
                "1071_0248309",
                VOCABULARY,
                GRAMMAR,
            ),
        ),
        typos=(
            Typo(2, "Mochtest", "1071_0024818"),
            Typo(2, "Schwimmen", "1071_0024818"),
        ),
        # MERLIN keeps "Konntest"; a model may correct it to "Könntest".
        neutrals=(Neutral(3, "Konntest", "1071_0248309"),),
        correct_messages=(1, 4),
        partner_questions=(("Wochenende", "weekend"), ("mitbringen", "bring")),
    ),
    AnalysisCase(
        id="au-pair",
        history=(
            _partner(
                "Hallo! Du warst doch als Au-pair in Deutschland. Wie lange warst "
                "du bei der Familie?"
            ),
            _learner("Ich habe etwa ein Vierteljahr bei meiner Gastfamilie."),
            _partner("Und, wie hat es dir dort gefallen?"),
            # Correct in MERLIN 1023_0108304.
            _learner("Leider bin ich sehr enttäuscht."),
            _partner("Oh nein, das tut mir leid. Erzähl mal."),
            _learner(
                "Ich soll mit der Gastfamilie wohnen, leider habe ich in einen "
                "Garage gewohnt."
            ),
            _partner("In einer Garage! Das ist ja schrecklich."),
            _learner("Ich konnte auch nicht Deutsch lernen"),
            _learner("Ich arbeite jeden tag zu viel und ich bekomme nur wenig Gehalt."),
        ),
        mistakes=(
            _gold(
                1,
                "habe",
                "war",
                "Wortwahl: sein für den Aufenthalt (ich war bei ...)",
                "1023_0108885",
                VOCABULARY,
            ),
            _gold(
                3,
                "einen Garage",
                "einer Garage",
                "in + Dativ (wo?), die Garage: in einer Garage",
                "1023_0108304",
                GRAMMAR,
            ),
            _gold(
                4,
                "nicht Deutsch",
                "kein Deutsch",
                "Negation eines Nomens ohne Artikel mit kein",
                "1023_0109249",
                GRAMMAR,
            ),
        ),
        typos=(Typo(5, "tag", "1023_0108992"),),
        neutrals=(),
        correct_messages=(2,),
        partner_questions=(("wie lange", "how long"), ("gefallen", "like", "enjoy")),
    ),
    AnalysisCase(
        id="wohnen-miete",
        history=(
            _partner("Du kennst doch die Stadt gut. Wo wohnt man hier am besten?"),
            _learner("Desto näher zum Bahnhof, desto höher der Mietzins."),
            _partner("Das stimmt, am Bahnhof ist es teuer."),
            _learner(
                "Ein Haus kostet teuer und alle Reperaturenkosten liegen auf dem "
                "Besitzer."
            ),
            # Correct in MERLIN 1031_0003065.
            _learner("Die Wohnungen in Mehrfamilienhäusern sind teuer."),
            _partner(
                "Ich zahle 800 Euro warm für zwei Zimmer. Gibt es bei dir eine "
                "Haltestelle in der Nähe?"
            ),
            _learner("Ich möchte gern wissen wie hoch die Miete sind."),
            _learner(
                "Hier giebt es auch ziemlich viele Menschen, die allein wohnen und "
                "leben."
            ),
        ),
        mistakes=(
            _gold(
                1,
                "Desto näher",
                "Je näher",
                "Wortwahl: je ... desto",
                "1031_0003357",
                VOCABULARY,
            ),
            _gold(
                2,
                "kostet teuer",
                "kostet viel",
                "Wortwahl: etwas kostet viel, ist aber teuer",
                "1031_0003035",
                VOCABULARY,
            ),
            _gold(
                4,
                "Miete sind",
                "Miete ist",
                "Subjekt-Verb-Kongruenz: die Miete ist",
                "1091_0000199",
                GRAMMAR,
            ),
        ),
        typos=(Typo(5, "giebt", "1031_0003383"),),
        # Spelling and compound form at once ("Reparaturkosten").
        neutrals=(Neutral(2, "Reperaturenkosten", "1031_0003035"),),
        correct_messages=(3,),
        partner_questions=(("wohnt", "live"), ("Haltestelle", "stop", "transport")),
    ),
)

# Case id -> the wrong fragment planted in a partner message. A reported item with
# it is an A1 violation (only the learner's messages are analysed).
PARTNER_PLANTS: tuple[tuple[str, str], ...] = (
    ("arbeit-pflegerin", "seit drei Jahre"),
    ("hund-koeln", "auf ihm"),
    ("baby-glueckwunsch", "in die Nacht"),
)


# --- turn: one clear mistake in the learner's last message ----------------------

TURN_CASES: tuple[TurnCase, ...] = (
    TurnCase(
        id="bus-bank",
        topic_key="bus-stop-weather",
        history=(
            _partner(
                "So ein Regen! Fahren Sie auch jeden Tag mit diesem Bus zur Arbeit?"
            ),
            _learner("Ich arbeite in eine Bank und das ist mein Traum."),
        ),
        wrong_forms=("in eine Bank",),
        correct_forms=("in einer Bank",),
        category=GRAMMAR,
        rule="in + Dativ (wo?): in einer Bank",
        source="1061_0120482",
    ),
    TurnCase(
        id="apotheke-silvester",
        topic_key="pharmacy",
        history=(
            _partner(
                "Guten Tag! Sie sehen erkältet aus. Seit wann fühlen Sie sich nicht gut?"
            ),
            _learner(
                "Die Silvesternacht hat mir leider kein Spaß gemacht, weil ich krank war."
            ),
        ),
        wrong_forms=("kein Spaß",),
        correct_forms=("keinen Spaß",),
        category=GRAMMAR,
        rule="Akkusativ maskulin: keinen Spaß",
        source="1061_0120497",
    ),
    TurnCase(
        id="verein-firma",
        topic_key="sports-club",
        history=(
            _partner(
                "Schön, dass du dich für unseren Verein interessierst! Arbeitest du "
                "hier in der Nähe?"
            ),
            _learner("Ich bin seit drei Monate bei Firma XY."),
        ),
        wrong_forms=("seit drei Monate",),
        correct_forms=("seit drei Monaten",),
        category=GRAMMAR,
        rule="Dativ Plural nach seit: seit drei Monaten",
        source="1061_0120430",
    ),
    TurnCase(
        id="zug-hamburg",
        topic_key="train-delay",
        history=(
            _partner(
                "Der Zug hat schon wieder 40 Minuten Verspätung. Fahren Sie weit?"
            ),
            _learner("Ich muss für vier Tagen nach Hamburg fahren."),
        ),
        wrong_forms=("vier Tagen",),
        correct_forms=("vier Tage",),
        category=GRAMMAR,
        rule="Akkusativ Plural nach für: für vier Tage",
        source="1091_0000168",
    ),
    TurnCase(
        id="hund-spielen",
        topic_key="dog-walk",
        history=(
            _partner(
                "Dein Hund ist wirklich lieb. Ich habe leider keinen eigenen Hund."
            ),
            _learner("Du Kannst mit ihn spielen."),
        ),
        wrong_forms=("mit ihn",),
        correct_forms=("mit ihm",),
        category=GRAMMAR,
        rule="Dativ nach mit: mit ihm",
        source="1091_0000237",
    ),
    TurnCase(
        id="treppenhaus-arbeit",
        topic_key="neighbour-stairwell",
        history=(
            _partner(
                "Hallo! Dich sieht man ja kaum noch. Gibt es etwas Neues bei dir?"
            ),
            _learner("Ich habe einen neue Arbeit gefunden."),
        ),
        wrong_forms=("einen neue Arbeit",),
        correct_forms=("eine neue Arbeit", "die neue Arbeit", "deine neue Arbeit"),
        category=GRAMMAR,
        rule="Genus: die Arbeit, also eine neue Arbeit",
        source="1061_0120495",
    ),
    TurnCase(
        id="kollege-leute",
        topic_key="colleague-weekend",
        history=(
            _partner("Sag mal, gefällt dir eigentlich die Arbeit hier im Büro?"),
            _learner("Das macht mir Spaß, mit Leute zu arbeiten."),
        ),
        wrong_forms=("mit Leute",),
        correct_forms=("mit Leuten",),
        category=GRAMMAR,
        rule="Dativ Plural nach mit: mit Leuten",
        source="1061_0120492",
    ),
    TurnCase(
        id="spielplatz-baby",
        topic_key="playground",
        history=(
            _partner("Übrigens: Wir bekommen im Sommer noch ein Baby!"),
            _learner("ich bin sehr Glück für euch."),
        ),
        wrong_forms=("sehr Glück",),
        correct_forms=("glücklich",),
        category=VOCABULARY,
        rule="Wortart: Adjektiv glücklich statt Nomen Glück",
        source="1071_0024867",
    ),
    TurnCase(
        id="treppenhaus-besuch",
        topic_key="neighbour-stairwell",
        history=(
            _partner("Ich bringe dir morgen Nachmittag den Kuchen vorbei, okay?"),
            _learner("Ich freue mich für deinen Besuch."),
        ),
        wrong_forms=("für deinen Besuch", "für meinen Besuch"),
        correct_forms=("auf deinen Besuch", "auf meinen Besuch"),
        category=VOCABULARY,
        rule="feste Präposition des Verbs: sich freuen auf",
        source="1061_0120456",
    ),
    TurnCase(
        id="paket-hilfe",
        topic_key="neighbour-parcel",
        history=(
            _partner("Hier ist dein Paket. Es war ziemlich schwer!"),
            _learner("Vielen DanK für deine helfen."),
        ),
        wrong_forms=("deine helfen",),
        correct_forms=("Hilfe",),
        category=VOCABULARY,
        rule="Wortart: Nomen Hilfe statt Verb helfen",
        source="1091_0000237",
    ),
    TurnCase(
        id="verein-alter",
        topic_key="sports-club",
        history=(
            _partner("Hast du schon einmal in einem Verein Fußball gespielt?"),
            _learner("Ich habe keine erfahrung und ich habe 17 Jahre Alt."),
        ),
        wrong_forms=("habe 17 Jahre", "hast 17 Jahre"),
        correct_forms=("bin 17 Jahre", "bist 17 Jahre", "bist 17"),
        category=VOCABULARY,
        rule="Wortwahl: das Alter mit sein (ich bin 17 Jahre alt)",
        source="1023_0104203",
    ),
    TurnCase(
        id="paket-bitte",
        topic_key="neighbour-parcel",
        history=(
            _partner("Hallo! Dein Paket liegt schon hier im Flur."),
            _learner("Ich habe eine Bitte für dich."),
        ),
        wrong_forms=("Bitte für dich", "Bitte für mich"),
        correct_forms=("Bitte an dich", "Bitte an mich"),
        category=VOCABULARY,
        rule="feste Präposition des Nomens: eine Bitte an jemanden",
        source="1091_0000055",
    ),
    TurnCase(
        id="hund-nachricht",
        topic_key="dog-walk",
        history=(
            _partner("Hallo! Hast du meine Nachricht wegen Samstag bekommen?"),
            _learner("Ich frohe mich, dass du mir geschrieben hast."),
        ),
        wrong_forms=("frohe mich",),
        correct_forms=("freue mich", "freust dich", "dich freust", "mich freue"),
        category=VOCABULARY,
        rule="Wortwahl: sich freuen (Verb); froh ist ein Adjektiv",
        source="1061_0120350",
    ),
    TurnCase(
        id="verein-pruefung",
        topic_key="sports-club",
        history=(
            _partner(
                "Stell dir vor, ich habe die Prüfung für den Trainerschein bestanden!"
            ),
            _learner("Ich freue mich sehr dazu."),
        ),
        wrong_forms=("sehr dazu", "dich dazu"),
        correct_forms=("darüber",),
        category=VOCABULARY,
        rule="Präpositionaladverb zu sich freuen über: darüber",
        source="1061_0120343",
    ),
    TurnCase(
        id="treppenhaus-baby",
        topic_key="neighbour-stairwell",
        history=(
            _partner(
                "Unser Baby ist jetzt zwei Wochen alt und schläft zum Glück viel."
            ),
            _learner("Kann ich nächste Woche euch besuchen?"),
        ),
        wrong_forms=("nächste Woche euch", "nächste Woche uns"),
        correct_forms=("euch nächste Woche", "uns nächste Woche"),
        category=WORD_ORDER,
        rule="unbetontes Pronomen vor der Zeitangabe im Mittelfeld",
        source="1071_0024834",
    ),
    TurnCase(
        id="hund-urlaub",
        topic_key="dog-walk",
        history=(
            _partner("Fährst du im Sommer weg?"),
            _learner("Ich kann leider nicht mein Haustier mitnehmen."),
        ),
        wrong_forms=("nicht mein Haustier", "nicht dein Haustier", "nicht deinen Hund"),
        correct_forms=("Haustier nicht", "Hund nicht", "ihn nicht"),
        category=WORD_ORDER,
        rule="nicht steht vor dem Infinitiv am Satzende, nach dem Objekt",
        source="1091_0000219",
    ),
    TurnCase(
        id="kollege-silvester",
        topic_key="colleague-weekend",
        history=(
            _partner("Und, was hast du an Silvester gemacht?"),
            _learner("Die Silvesternacht habe ich gekocht für meine Familie."),
        ),
        wrong_forms=("gekocht für meine Familie", "gekocht für deine Familie"),
        correct_forms=(
            "für meine Familie gekocht",
            "für deine Familie gekocht",
            "für die Familie gekocht",
        ),
        category=WORD_ORDER,
        rule="Satzklammer: das Partizip steht am Satzende",
        source="1061_0120482",
    ),
    TurnCase(
        id="party-treffen",
        topic_key="birthday-party",
        history=(
            _partner("Es war wirklich schön, dich heute kennenzulernen!"),
            _learner("Ich hoffe dass wir können uns bald treffen."),
        ),
        # Only the subordinate clause is wrong: "wir können uns ..." is a correct
        # main clause, so the wrong form keeps "dass".
        wrong_forms=("dass wir können",),
        correct_forms=("dass wir uns", "treffen können"),
        category=WORD_ORDER,
        rule="Verbendstellung im dass-Satz",
        source="1061_0120884",
    ),
    TurnCase(
        id="kollege-kaffee",
        topic_key="colleague-weekend",
        history=(
            _partner("Wollen wir nach der Arbeit noch einen Kaffee trinken?"),
            # Correct in MERLIN 1091_0000252.
            _learner("Mein Großvater ist krank und liegt im Krankenhaus."),
            _partner("Oh nein, das tut mir leid."),
            _learner("Deshalb könnten wir uns nicht jetzt treffen."),
        ),
        wrong_forms=("nicht jetzt",),
        correct_forms=("jetzt nicht",),
        category=WORD_ORDER,
        rule="nicht steht nach der Zeitangabe jetzt",
        source="1061_0120490",
    ),
    TurnCase(
        id="party-frau",
        topic_key="birthday-party",
        history=(
            _partner("Meine Frau und ich kommen am Samstag auch zu Lenas Party."),
            _learner("Ich freue sehr mich auf dich und deine Frau."),
        ),
        wrong_forms=("freue sehr mich", "sehr mich"),
        correct_forms=("mich sehr", "uns sehr", "dich sehr"),
        category=WORD_ORDER,
        rule="Reflexivpronomen direkt nach dem Verb, vor dem Adverb",
        source="1071_0024834",
    ),
)


# --- memory: an opening turn after an earlier conversation in the same scene ----

MEMORY_CASES: tuple[MemoryCase, ...] = (
    MemoryCase(
        id="memory-bakery",
        topic_key="bakery",
        scene_notes=(
            (
                "The learner ordered four rolls and a coffee to go.",
                "The partner asked whether the learner wanted a bag for the rolls.",
                "The partner asked whether the learner lives in the neighbourhood.",
            ),
        ),
        forbidden=(("Tüte",), ("wohnen Sie", "wohnst du", "Nachbarschaft")),
    ),
    MemoryCase(
        id="memory-dog-walk",
        topic_key="dog-walk",
        scene_notes=(
            (
                "The partner asked what the learner's dog is called.",
                "The partner asked how old the learner's dog is.",
                "The partner said that their own dog is a beagle called Bruno.",
            ),
        ),
        forbidden=(
            ("heißt dein Hund", "heißt Ihr Hund", "heißt er", "heißt sie", "Name"),
            ("wie alt",),
        ),
    ),
    MemoryCase(
        id="memory-hairdresser",
        topic_key="hairdresser",
        scene_notes=(
            (
                "The partner asked how short the learner wanted the hair on the sides.",
                "The partner asked whether the learner wanted the hair washed first.",
                "The partner cut the hair shorter on the sides and kept the top long.",
            ),
        ),
        forbidden=(("wie kurz",), ("waschen",)),
    ),
    MemoryCase(
        id="memory-restaurant",
        topic_key="restaurant",
        scene_notes=(
            (
                "The partner asked whether the learner had a reservation.",
                "The partner asked what the learner wanted to drink.",
                "The learner ordered a Schnitzel with potato salad.",
            ),
        ),
        forbidden=(("reserviert", "Reservierung"), ("trinken",)),
    ),
    MemoryCase(
        id="memory-train-delay",
        topic_key="train-delay",
        scene_notes=(
            (
                "The partner asked where the learner was travelling to.",
                "The partner asked whether the learner had a seat reservation.",
                "The partner said they travel to Munich for work every week.",
            ),
        ),
        forbidden=(("wohin",), ("Platzreservierung", "reserviert", "Reservierung")),
    ),
)


# --- latency: one long conversation for timing the analysis ---------------------

# Every learner message is a sentence of MERLIN text 1061_0120880 (B2), in its
# order; the partner messages are written for this eval. No gold mistakes.
LATENCY_CASE: History = (
    _partner("Hallo! Hast du meinen Brief mit den Neujahrsgrüßen bekommen?"),
    _learner("danke für deinen Brief."),
    _partner("Gern! Erzähl mal, wie war deine Silvesternacht?"),
    _learner("Die Silvesternacht habe ich diese Jahr meiner Freundin gefeiert."),
    _partner("Schön! Habt ihr zusammen gekocht?"),
    _learner("Maria hat gekocht und ich habe nur geholfen."),
    _partner("Was hast du denn gemacht?"),
    _learner("Ich habe eigentlich nur Kartoffeln geschält."),
    _partner("Haha, das ist auch wichtig!"),
    _learner("Wie du weißt, ich kann nicht so gut kochen."),
    _partner(
        "Ja, ich erinnere mich an deine Spaghetti. Und was habt ihr nach dem "
        "Essen gemacht?"
    ),
    _learner('Danach haben wir ein DVD geguckt "INCEPTION".'),
    _partner("Den Film kenne ich noch nicht. Woher hattet ihr die DVD?"),
    _learner("Maria hat von ihrer Freundin ausgeliehen."),
    _partner("Und, wie war der Film?"),
    _learner("Ich fand den Film echt super."),
    _partner("Dann muss ich ihn mir auch ansehen."),
    _learner("Wenn du Zeit hast, solltest du einmal gucken.!!!"),
    _partner("Mache ich! Habt ihr um Mitternacht auch das Feuerwerk gesehen?"),
    _learner(
        "Um 12 Uhr sind wir auf dem Berg hoch gegangen, wo wir uns das Feuerwerk "
        "richtig gut sehen konnten."
    ),
    _partner(
        "Vom Berg aus ist das bestimmt wunderschön. Hast du Wünsche für das neue Jahr?"
    ),
    _learner("Meine Wünsche für das neue Jahr ist dass ich mehr Freizeit habe."),
    _partner("Das wünsche ich mir auch! Hast du schon Pläne für den Frühling?"),
    _learner("Und ich kann im Frühling nach Belgien fahren."),
    _partner("Toll! Warst du schon einmal in Belgien?"),
    _learner(
        "Ich war noch nie in Belgien aber Maria war schon vieles mal da und sie hat "
        "viel von Belgien erzählt."
    ),
    _partner("Ich war letztes Jahr in Brüssel. Die Stadt hat mir sehr gut gefallen."),
    _learner("Wenn du mich besuchst, können wir vielleicht zusammen fahren."),
    _partner("Das ist eine super Idee! Und wie läuft es bei der Arbeit?"),
    _learner(
        "Ich weiß, dass ich schon lange nichts mehr von meiner Arbeit erzählt habe."
    ),
    _partner("Stimmt, du hast lange nichts erzählt."),
    _learner(
        "Weil meine Arbeit jetzt langweilig ist, habe ich nicht mehr viel zu erzählen."
    ),
    _partner("Oh, das tut mir leid. Das klingt nicht so gut."),
    _learner("Ich habe oft Langeweile aber keine Sorge!"),
    _partner("Wirklich alles okay bei dir?"),
    _learner("Alles ist in Ordnung."),
    _partner("Da bin ich aber froh."),
    _learner("Es geht immer wieder besser."),
    _partner("Das freut mich. Schreib mir bald wieder!"),
    _learner("Ich freue mich wenn du mir zürück schreibst."),
)
