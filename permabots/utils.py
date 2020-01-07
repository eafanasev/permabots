# from telegram import emoji
# TODO: use https://github.com/carpedm20/emoji
from six import iteritems, PY2


def create_emoji_context():
    context = {}
    # for key, value in iteritems(emoji.Emoji.__dict__):
    #     if '__' not in key:
    #         if PY2:
    #             value = value.decode('utf-8')
    #         context[key.lower().replace(" ", "_")] = value
    return context
