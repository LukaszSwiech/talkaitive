"""Fixed list of conversation topics.

The list can be changed without a migration: a conversation keeps its own copy of
the topic title and scenario (see `Conversation.topic_title` / `topic_scenario`).
`title` is shown to the user (the UI is in English); `scenario` goes to the model.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    title: str
    scenario: str


TOPICS: tuple[Topic, ...] = (
    Topic(
        key="dog-walk",
        title="Walking the dog: chatting with another dog owner",
        scenario=(
            "You are another dog owner met in a park in Germany. Your dog and the "
            "learner's dog are playing; start a friendly chat about the dogs."
        ),
    ),
    Topic(
        key="supermarket",
        title="Supermarket: asking where to find something",
        scenario=(
            "You are a supermarket employee stocking shelves. The learner is a "
            "customer looking for a product and asks you where to find it."
        ),
    ),
    Topic(
        key="bakery",
        title="Bakery: ordering breakfast rolls",
        scenario=(
            "You are a shop assistant in a German bakery. The learner wants to "
            "order breakfast rolls and maybe a coffee; ask what they would like."
        ),
    ),
    Topic(
        key="neighbour-stairwell",
        title="Neighbour in the stairwell: small talk",
        scenario=(
            "You are a neighbour who lives in the same building. You meet the "
            "learner in the stairwell and make polite small talk."
        ),
    ),
    Topic(
        key="neighbour-parcel",
        title="Picking up a parcel from a neighbour",
        scenario=(
            "You are a neighbour who accepted a parcel for the learner. The "
            "learner rings your door to pick it up; chat briefly while handing it over."
        ),
    ),
    Topic(
        key="doctor-appointment",
        title="Calling a doctor's office for an appointment",
        scenario=(
            "You are the receptionist at a doctor's office on the phone. The "
            "learner calls to book an appointment; ask about the reason and a "
            "suitable day and time."
        ),
    ),
    Topic(
        key="pharmacy",
        title="Pharmacy: asking for something for a cold",
        scenario=(
            "You are a pharmacist. The learner comes in with a cold and asks for "
            "something to help; ask about the symptoms and recommend a remedy."
        ),
    ),
    Topic(
        key="colleague-weekend",
        title="Weekend plans with a colleague",
        scenario=(
            "You are a friendly colleague at the office on a Friday afternoon. "
            "Ask the learner about their weekend plans and share your own."
        ),
    ),
    Topic(
        key="playground",
        title="Playground: chatting with another parent",
        scenario=(
            "You are a parent at a playground whose child is playing near the "
            "learner's child. Start a casual conversation about the kids."
        ),
    ),
    Topic(
        key="post-office",
        title="Post office: sending a parcel",
        scenario=(
            "You are a clerk at a German post office. The learner wants to send a "
            "parcel; ask about the destination, weight and shipping options."
        ),
    ),
    Topic(
        key="hairdresser",
        title="Hairdresser: explaining the cut you want",
        scenario=(
            "You are a hairdresser. The learner sits in your chair and explains "
            "the haircut they want; ask clarifying questions about length and style."
        ),
    ),
    Topic(
        key="restaurant",
        title="Restaurant: ordering and paying",
        scenario=(
            "You are a waiter in a restaurant in Germany. Take the learner's "
            "order, answer questions about the menu, and handle the bill at the end."
        ),
    ),
    Topic(
        key="public-transport",
        title="Public transport: ticket problem and directions",
        scenario=(
            "You are a transit employee at a station. The learner has a problem "
            "with their ticket and also needs directions to reach their destination."
        ),
    ),
    Topic(
        key="train-delay",
        title="Train delay: talking with a fellow passenger",
        scenario=(
            "You are a fellow passenger waiting on a platform where the train is "
            "delayed. Chat with the learner about the delay and what to do."
        ),
    ),
    Topic(
        key="landlord-heating",
        title="Reporting a broken heater to the landlord",
        scenario=(
            "You are the landlord. The learner calls to report that the heater in "
            "their flat is broken; ask for details and arrange a repair."
        ),
    ),
    Topic(
        key="registration-office",
        title="Registering your address at the Bürgeramt",
        scenario=(
            "You are a clerk at the Bürgeramt (citizens' office). The learner "
            "wants to register their new address; ask for the documents and the "
            "details you need."
        ),
    ),
    Topic(
        key="bus-stop-weather",
        title="Weather small talk at the bus stop",
        scenario=(
            "You are a stranger waiting at a bus stop on a rainy day. Make small "
            "talk with the learner about the weather and the bus."
        ),
    ),
    Topic(
        key="birthday-party",
        title="Birthday party: meeting a friend's friends",
        scenario=(
            "You are a guest at a friend's birthday party who has not met the "
            "learner before. Introduce yourself and get to know them."
        ),
    ),
    Topic(
        key="sports-club",
        title="Joining a local sports club",
        scenario=(
            "You are a staff member of a local sports club (Verein). The learner "
            "asks about joining; explain trial sessions, fees and schedule."
        ),
    ),
    Topic(
        key="car-workshop",
        title="Booking a tyre change at a car workshop",
        scenario=(
            "You are a service advisor at a car workshop. The learner wants to "
            "book a tyre change; ask about the car and offer an appointment."
        ),
    ),
)

_TOPICS_BY_KEY = {topic.key: topic for topic in TOPICS}


def get_topic(key: str) -> Topic | None:
    return _TOPICS_BY_KEY.get(key)
