"""Fixed list of conversation topics.

The list can be changed without a migration: a conversation keeps its own copy of
the topic title and scenario (see `Conversation.topic_title` / `topic_scenario`).
The UI is in English. `name`, `subtitle`, `category` and `icon` are only shown on
the topic card on the home page and are not copied to the conversation. `title` is
the full topic line copied to the conversation and shown to the user there;
`scenario` goes to the model. `tests/test_topics.py` checks that every topic has
all card fields, a known category and an existing icon template.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    title: str
    scenario: str
    name: str = ""
    subtitle: str = ""
    category: str = ""
    icon: str = ""

    @property
    def icon_template(self) -> str:
        """Template path of the topic's icon (`accounts/templates/ui/icons/`).

        Render cards only from `TOPICS`: a `Topic` rebuilt from a conversation's copy
        has no icon, and its path would not exist.
        """
        return f"ui/icons/{self.icon}.svg"


@dataclass(frozen=True)
class Category:
    key: str
    label: str


# In display order on the home page.
CATEGORIES: tuple[Category, ...] = (
    Category(key="errands", label="Shops & errands"),
    Category(key="small-talk", label="Neighbours & small talk"),
    Category(key="appointments", label="Appointments & officials"),
    Category(key="social", label="Social life"),
)


TOPICS: tuple[Topic, ...] = (
    Topic(
        key="dog-walk",
        title="Walking the dog: chatting with another dog owner",
        name="Dog walk",
        subtitle="Chatting with another dog owner",
        category="small-talk",
        icon="dog",
        scenario=(
            "You are another dog owner met in a park in Germany. Your dog and the "
            "learner's dog are playing; start a friendly chat about the dogs."
        ),
    ),
    Topic(
        key="supermarket",
        title="Supermarket: asking where to find something",
        name="Supermarket",
        subtitle="Asking where to find something",
        category="errands",
        icon="shopping-cart",
        scenario=(
            "You are a supermarket employee stocking shelves. The learner is a "
            "customer looking for a product and asks you where to find it."
        ),
    ),
    Topic(
        key="bakery",
        title="Bakery: ordering breakfast rolls",
        name="Bakery",
        subtitle="Ordering breakfast rolls",
        category="errands",
        icon="bread",
        scenario=(
            "You are a shop assistant in a German bakery. The learner wants to "
            "order breakfast rolls and maybe a coffee; ask what they would like."
        ),
    ),
    Topic(
        key="neighbour-stairwell",
        title="Neighbour in the stairwell: small talk",
        name="Stairwell",
        subtitle="Small talk with a neighbour",
        category="small-talk",
        icon="stairs",
        scenario=(
            "You are a neighbour who lives in the same building. You meet the "
            "learner in the stairwell and make polite small talk."
        ),
    ),
    Topic(
        key="neighbour-parcel",
        title="Picking up a parcel from a neighbour",
        name="Parcel",
        subtitle="Picking it up from a neighbour",
        category="small-talk",
        icon="package",
        scenario=(
            "You are a neighbour who accepted a parcel for the learner. The "
            "learner rings your door to pick it up; chat briefly while handing it over."
        ),
    ),
    Topic(
        key="doctor-appointment",
        title="Calling a doctor's office for an appointment",
        name="Doctor",
        subtitle="Calling for an appointment",
        category="appointments",
        icon="stethoscope",
        scenario=(
            "You are the receptionist at a doctor's office on the phone. The "
            "learner calls to book an appointment; ask about the reason and a "
            "suitable day and time."
        ),
    ),
    Topic(
        key="pharmacy",
        title="Pharmacy: asking for something for a cold",
        name="Pharmacy",
        subtitle="Something for a cold",
        category="errands",
        icon="pill",
        scenario=(
            "You are a pharmacist. The learner comes in with a cold and asks for "
            "something to help; ask about the symptoms and recommend a remedy."
        ),
    ),
    Topic(
        key="colleague-weekend",
        title="Weekend plans with a colleague",
        name="Weekend plans",
        subtitle="Chatting with a colleague",
        category="social",
        icon="briefcase",
        scenario=(
            "You are a friendly colleague at the office on a Friday afternoon. "
            "Ask the learner about their weekend plans and share your own."
        ),
    ),
    Topic(
        key="playground",
        title="Playground: chatting with another parent",
        name="Playground",
        subtitle="Chatting with another parent",
        category="small-talk",
        icon="horse-toy",
        scenario=(
            "You are a parent at a playground whose child is playing near the "
            "learner's child. Start a casual conversation about the kids."
        ),
    ),
    Topic(
        key="post-office",
        title="Post office: sending a parcel",
        name="Post office",
        subtitle="Sending a parcel",
        category="errands",
        icon="mail",
        scenario=(
            "You are a clerk at a German post office. The learner wants to send a "
            "parcel; ask about the destination, weight and shipping options."
        ),
    ),
    Topic(
        key="hairdresser",
        title="Hairdresser: explaining the cut you want",
        name="Hairdresser",
        subtitle="Explaining the cut you want",
        category="errands",
        icon="scissors",
        scenario=(
            "You are a hairdresser. The learner sits in your chair and explains "
            "the haircut they want; ask clarifying questions about length and style."
        ),
    ),
    Topic(
        key="restaurant",
        title="Restaurant: ordering and paying",
        name="Restaurant",
        subtitle="Ordering and paying",
        category="social",
        icon="tools-kitchen-2",
        scenario=(
            "You are a waiter in a restaurant in Germany. Take the learner's "
            "order, answer questions about the menu, and handle the bill at the end."
        ),
    ),
    Topic(
        key="public-transport",
        title="Public transport: ticket problem and directions",
        name="Public transport",
        subtitle="Ticket problem and directions",
        category="appointments",
        icon="bus",
        scenario=(
            "You are a transit employee at a station. The learner has a problem "
            "with their ticket and also needs directions to reach their destination."
        ),
    ),
    Topic(
        key="train-delay",
        title="Train delay: talking with a fellow passenger",
        name="Train delay",
        subtitle="Talking with a fellow passenger",
        category="small-talk",
        icon="train",
        scenario=(
            "You are a fellow passenger waiting on a platform where the train is "
            "delayed. Chat with the learner about the delay and what to do."
        ),
    ),
    Topic(
        key="landlord-heating",
        title="Reporting a broken heater to the landlord",
        name="Broken heater",
        subtitle="Reporting it to the landlord",
        category="appointments",
        icon="flame",
        scenario=(
            "You are the landlord. The learner calls to report that the heater in "
            "their flat is broken; ask for details and arrange a repair."
        ),
    ),
    Topic(
        key="registration-office",
        title="Registering your address at the Bürgeramt",
        name="Bürgeramt",
        subtitle="Registering your address",
        category="appointments",
        icon="id",
        scenario=(
            "You are a clerk at the Bürgeramt (citizens' office). The learner "
            "wants to register their new address; ask for the documents and the "
            "details you need."
        ),
    ),
    Topic(
        key="bus-stop-weather",
        title="Weather small talk at the bus stop",
        name="Bus stop",
        subtitle="Weather small talk",
        category="small-talk",
        icon="cloud-rain",
        scenario=(
            "You are a stranger waiting at a bus stop on a rainy day. Make small "
            "talk with the learner about the weather and the bus."
        ),
    ),
    Topic(
        key="birthday-party",
        title="Birthday party: meeting a friend's friends",
        name="Birthday party",
        subtitle="Meeting a friend's friends",
        category="social",
        icon="cake",
        scenario=(
            "You are a guest at a friend's birthday party who has not met the "
            "learner before. Introduce yourself and get to know them."
        ),
    ),
    Topic(
        key="sports-club",
        title="Joining a local sports club",
        name="Sports club",
        subtitle="Joining a local club",
        category="social",
        icon="ball-football",
        scenario=(
            "You are a staff member of a local sports club (Verein). The learner "
            "asks about joining; explain trial sessions, fees and schedule."
        ),
    ),
    Topic(
        key="car-workshop",
        title="Booking a tyre change at a car workshop",
        name="Car workshop",
        subtitle="Booking a tyre change",
        category="errands",
        icon="car",
        scenario=(
            "You are a service advisor at a car workshop. The learner wants to "
            "book a tyre change; ask about the car and offer an appointment."
        ),
    ),
)

_TOPICS_BY_KEY = {topic.key: topic for topic in TOPICS}


def get_topic(key: str) -> Topic | None:
    return _TOPICS_BY_KEY.get(key)


def topics_by_category() -> list[tuple[Category, list[Topic]]]:
    """Topics grouped for the home page: categories in `CATEGORIES` order, topics
    inside each category in `TOPICS` order."""
    return [
        (category, [topic for topic in TOPICS if topic.category == category.key])
        for category in CATEGORIES
    ]
