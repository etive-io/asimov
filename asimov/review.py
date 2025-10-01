"""
Review-related code.

Note
----
This code does not directly relate to the review of *asimov*
but rather to the review of events which it has been used to analyse.
"""

from datetime import datetime

STATES = {"REJECTED", "APPROVED", "PREFERRED", "DEPRECATED"}
review_map = {
    "deprecated": "warning",
    "none": "default",
    "approved": "success",
    "rejected": "danger",
    "checked": "info",
}


class Review:
    """
    A class to record the review status of a given production.
    """

    def __init__(self):
        self.messages = []

    def __len__(self):
        return len(self.messages)

    def __getitem__(self, item):
        return self.messages[item]

    def add(self, review_message):
        """
        Add a new review message to an event.
        """
        self.messages.append(review_message)
        self.messages = sorted(self.messages, key=lambda k: k.timestamp)

    @property
    def status(self):
        status = None
        for message in self.messages:
            if message.status:
                status = message.status
        return status

    def to_dicts(self):
        output = []
        for message in self.messages:
            output.append(message.to_dict())
        return output

    @classmethod
    def from_dict(cls, messages_list, production):
        """parse a dictionary into review"""
        messages = []
        for message in messages_list:
            messages.append(
                ReviewMessage.from_dict(dictionary=message, production=production)
            )

        review_ob = cls()
        messages = sorted(messages, key=lambda k: k.timestamp)
        review_ob.messages = messages
        return review_ob


class ReviewMessage:
    """
    A review message.
    """

    def __init__(self, message, production, status=None, timestamp=None):
        """
        Review messages are individual messages related to the review of a production.

        Parameters
        ----------
        message : str
           The review message. This can be free-form text.
        production : `Asimov.event.Production`
           The production which this message is attached to.
        state: str, {"REJECTED", "APPROVED", "PREFERRED", "DEPRECATED"}
           The review state. This is optional, and a message can
           be added without a review state. If a review state is added
           it will over-ride any previously added review messages.
        timestamp: str, optional
           The timestamp for the message, optional, should be
           formatted "%Y-%m-%d %H:%M:%S".
        """

        self.message = message

        if status is not None:
            if status.upper() in STATES:
                self.status = status.upper()
            else:
                raise ValueError(f"{status} is not a recognised review state.")
        else:
            self.status = None

        if timestamp:
            self.timestamp = (
                timestamp  # datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
            )
        else:
            self.timestamp = datetime.now()

    def to_dict(self):
        """
        Serialise this object as a dictionary
        """
        out = {}
        out["message"] = self.message
        out["timestamp"] = str(self.timestamp)
        out["status"] = self.status

        return out

    @classmethod
    def from_dict(cls, dictionary, production):
        """
        Create a review message from a dictionary.
        """
        default = {"status": None, "message": None, "timestamp": None}
        default.update(dictionary)
        if isinstance(default["timestamp"], str):
            timestamp = datetime.strptime(default["timestamp"], "%Y-%m-%d %H:%M:%S.%f")
        else:
            timestamp = default["timestamp"]
        message_ob = cls(
            message=default["message"],
            production=production,
            status=default["status"],
            timestamp=timestamp,
        )
        return message_ob

    def html(self):
        """
        Return an HTML representation of this review message.
        """
        review_row = ""
        if self.status:
            review_row += f"""<div class="asimov-review alert alert-{review_map[self.status.lower()]}" role="alert">
            <strong>{self.status}</strong>  """
        else:
            review_row += """<div class="alert alert-light" role="alert">"""
        if self.message:
            review_row += f"{self.message}"
        review_row += "</div>"
        return review_row
