#!/usr/bin/env python3
"""
Jarvis Notes Module.

All commands that require persistent storage belong here. This includes
logging, tells, and quotes.
"""
###############################################################################
# Module Imports
###############################################################################

import arrow
import random
import re
import peewee
import playhouse.sqlite_ext

from . import core, lexicon, parser


###############################################################################
# Database ORM Classes
###############################################################################


db = playhouse.sqlite_ext.SqliteExtDatabase('jarvis.db', journal_mode='WAL')


class BaseModel(peewee.Model):
    """Peewee Base Table/Model Class."""

    class Meta:
        """Bind Model definitions to the database."""

        database = db


class Tell(BaseModel):
    """Database Tell Table."""

    sender = peewee.CharField()
    recipient = peewee.CharField(index=True)
    topic = peewee.CharField(null=True)
    text = peewee.TextField()
    time = peewee.DateTimeField()


class Message(BaseModel):
    """Database Message Table."""

    user = peewee.CharField(index=True)
    channel = peewee.CharField()
    time = peewee.DateTimeField()
    text = peewee.TextField()


class Quote(BaseModel):
    """Database Quote Table."""

    user = peewee.CharField(index=True)
    channel = peewee.CharField()
    time = peewee.DateTimeField()
    text = peewee.TextField()


class Rem(BaseModel):
    """Database Rem Table."""

    user = peewee.CharField(index=True)
    channel = peewee.CharField()
    text = peewee.TextField()


class Subscriber(BaseModel):
    """Database Subscriber Table."""

    user = peewee.CharField()
    topic = peewee.CharField(index=True)


class Restricted(BaseModel):
    """Database Restricted Table."""

    topic = peewee.CharField(index=True)


class Alert(BaseModel):
    """Database Alert Table."""

    user = peewee.CharField(index=True)
    time = peewee.DateTimeField()
    text = peewee.TextField()

###############################################################################


def init():
    """Initialize the database, create missing tables."""
    db.connect()
    db.create_tables(
        [Tell, Message, Quote, Rem, Subscriber, Restricted, Alert], safe=True)


def logevent(inp):
    """Log input into the database."""
    Message.create(
        user=inp.user, channel=inp.channel,
        time=arrow.utcnow().timestamp, text=inp.text)


###############################################################################
# Tells
###############################################################################


@core.command
@parser.tell
def tell(inp, *, user, topic, message):
    """
    Send messages to other users.

    Saves the message and delivers them to the target next time they're in
    the same channel with the bot. The target is either a single user, or a
    tell topic. In the later case, all users subscribed to the topic at the
    moment the tell it sent will recieve the message.
    """
    if topic:
        users = Subscriber.select().where(Subscriber.topic == topic)
        users = [i.user for i in users]
        if not users:
            return lexicon.topic.no_subscribers
    else:
        users = [user]

    data = dict(
        sender=inp.user,
        text=message,
        time=arrow.utcnow().timestamp,
        topic=bool(topic))
    Tell.insert_many(dict(recipient=i, **data) for i in users).execute()

    msg = lexicon.topic.send if topic else lexicon.tell.send
    return msg.format(count=len(users))


@core.command
@core.private
@core.multiline
def get_tells(inp):
    """Retrieve incoming messages."""
    query = Tell.select().where(Tell.recipient == inp.user.lower()).execute()
    for tell in query:

        time = arrow.get(tell.time).humanize()
        msg = lexicon.topic.get if tell.topic else lexicon.tell.get

        yield msg.format(
            name=tell.sender,
            time=time,
            topic=tell.topic,
            text=tell.text)
        tell.delete_instance()


@core.command
@core.notice
@parser.outbound
def outbound(inp, *, count, purge):
    """
    Access outbound tells.

    Outband tells are tells sent by the input user, which haven't been
    delivered to their targets yet.

    Ignores messages sent to tell topics.
    """
    query = Tell.select().where(
        peewee.fn.Lower(Tell.sender) == inp.user.lower(),
        Tell.topic.is_null())

    if not query.exists():
        return lexicon.tell.outbound.empty

    if count:
        msg = lexicon.tell.outbound.count
    elif purge:
        Tell.delete().where(
            peewee.fn.Lower(Tell.sender) == inp.user,
            Tell.topic.is_null()).execute()
        msg = lexicon.tell.outbound.purged

    users = ', '.join(sorted({i.recipient for i in query}))
    return msg.format(count=query.count(), users=users)


###############################################################################
# Seen
###############################################################################


@core.command
@core.lower_input
@parser.seen
def seen(inp, *, user, first):
    """Retrieve the first or the last message said by the user."""
    if user == core.config['irc']['nick']:
        return lexicon.seen.self

    order = Message.time if first else Message.time.desc()
    query = Message.select().where(
        peewee.fn.Lower(Message.user) == user,
        Message.channel == inp.channel).order_by(order)
    if not query.exists():
        return lexicon.seen.never

    seen = query.get()
    time = arrow.get(seen.time).humanize()
    msg = lexicon.seen.first if first else lexicon.seen.last
    return msg.format(user=seen.user, time=time, text=seen.text)


###############################################################################
# Quotes
###############################################################################


@core.command
#@core.parse_input(r'(?P<mode>add|del)?(?(mode) ).*')
def dispatch_quote(inp, *, mode):
    """!quote [add|del] [<user>] [<index>] -- Access users' quotes."""
    if mode == 'add':
        inp.text = inp.text[4:]
        return add_quote(inp)
    elif mode == 'del':
        inp.text = inp.text[4:]
        return del_quote(inp)
    return get_quote(inp)


#@core.parse_input(r'add ?{date}? {user} {message}')
def add_quote(inp, *, date, user, message):
    """!quote add [<date>] <user> <message> -- Save user's quote."""
    if Quote.select().where(
            Quote.user == user.lower(),
            Quote.channel == inp.channel,
            Quote.text == message).exists():
        return lexicon.quote.already_exists

    Quote.create(
        user=user.lower(),
        channel=inp.channel,
        time=date or arrow.utcnow().format('YYYY-MM-DD'),
        text=message)

    return lexicon.quote.saved


#@core.parse_input('del {user} {message}')
def del_quote(inp, *, user, message):
    """!quote del <user> <message> -- Delete the matching quote."""
    query = Quote.select().where(
        Quote.user == user.lower(),
        Quote.channel == inp.channel,
        Quote.text == message)

    if not query.exists():
        return lexicon.quote.not_found

    query.get().delete_instance()
    return lexicon.quote.deleted


@core.lower_input
#@core.parse_input(r'{user}? ?{index}?')
def get_quote(inp, *, user, index):
    """Retrieve a quote."""
    query = Quote.select().where(Quote.channel == inp.channel)
    if user:
        query = query.where(Quote.user == user)

    if not query.exists():
        return lexicon.quote.none_saved

    index = int(index or random.randint(1, query.count()))
    if index > query.count():
        return lexicon.input.bad_index
    quote = query.order_by(Quote.time).limit(1).offset(index - 1)[0]

    return '[{}/{}] {:.10} {}: {}'.format(
        index, query.count(), str(quote.time), quote.user, quote.text)


###############################################################################
# Memos
###############################################################################


@core.command
#@core.parse_input('{user} {message}')
def remember_user(inp, *, user, message):
    """!rem <user> <message> -- Make a memo about the user."""
    Rem.delete().where(
        Rem.user == user.lower(),
        Rem.channel == inp.channel).execute()

    Rem.create(user=user.lower(), channel=inp.channel, text=message)

    return lexicon.quote.saved


@core.command
@core.lower_input
#@core.parse_input(r'\?{user}')
def recall_user(inp, *, user):
    """?<user> -- Display the user's memo."""
    rem = Rem.select().where(
        Rem.user == user,
        Rem.channel == inp.channel)

    if rem.exists():
        return rem.get().text
    else:
        return lexicon.not_found.generic


###############################################################################
# Topics
###############################################################################


@core.command
@core.lower_input
#@core.parse_input('{topic}')
def subscribe_to_topic(inp, *, topic):
    """!sub <topic> -- Subscribe to topic."""
    if inp.channel != core.config['irc']['sssc']:
        if Restricted.select().where(
                Restricted.topic == topic).exists():
            return lexicon.denied

    if Subscriber.select().where(
            Subscriber.user == inp.user,
            Subscriber.topic == topic).exists():
        return lexicon.topic.already_subscribed

    Subscriber.create(user=inp.user, topic=topic)
    return lexicon.topic.subscribed.format(topic=topic)


@core.command
@core.lower_input
#@core.parse_input('{topic}')
def unsubscribe_from_topic(inp, *, topic):
    """!unsub <topic> -- Remove topic subscription."""
    query = Subscriber.select().where(
        Subscriber.user == inp.user,
        Subscriber.topic == topic)

    if not query.exists():
        return lexicon.topic.not_subscribed

    query.get().delete_instance()
    return lexicon.topic.unsubscribed.format(topic=topic)


@core.command
@core.notice
@core.lower_input
def get_topics_count(inp):
    """!topics -- Display the list of topics you're subscribed to."""
    query = Subscriber.select().where(Subscriber.user == inp.user)

    if not query.exists():
        return lexicon.topic.user_has_no_topics

    topics = [i.topic for i in query]
    return lexicon.topic.count.format(topics=', '.join(topics))


@core.command
@core.lower_input
#@core.parse_input('{topic}')
def restrict_topic(inp, *, topic):
    """!restrict <topic> -- Prevent users from subscribing to the topic."""
    if inp.channel != core.config['irc']['sssc']:
        return lexicon.denied

    if Restricted.select().where(Restricted.topic == topic).exists():
        return lexicon.topic.already_restricted

    Restricted.create(topic=topic)
    return lexicon.topic.restricted


@core.command
@core.lower_input
#@core.parse_input('{topic}')
def unrestrict_topic(inp, *, topic):
    """!restrict <topic> -- Lift restriction from the topic."""
    if inp._channel != core.config['irc']['sssc']:
        return lexicon.denied

    query = Restricted.select().where(Restricted.topic == topic)
    if not query.exists():
        return lexicon.topic.not_restricted

    query.get().delete_instance()
    return lexicon.topic.unrestricted


###############################################################################
# Alerts
###############################################################################


@core.command
#@core.parse_input(r'{date}|(?P<delay>(\d+[dhm])+) {message}')
def set_alert(inp, *, date, delay, message):
    """!alert [<date>|<delay>] <message> -- Remind your future self."""
    if date:
        alert = arrow.get(date)
        if alert < arrow.utcnow():
            return lexicon.alert.past

    elif delay:
        alert = arrow.utcnow()
        for length, unit in re.findall(r'(\d+)([dhm])', delay):
            unit = dict(d='days', h='hours', m='minutes')[unit]
            alert = alert.replace(**{unit: int(length)})

    Alert.create(user=inp.user.lower(), time=alert.timestamp, text=message)
    return lexicon.alert.set


@core.command
@core.private
@core.multiline
@core.lower_input
def get_alerts(inp):
    """Retrieve stored alerts."""
    now = arrow.utcnow()
    for alert in Alert.select().where(Alert.user == inp.user):
        if arrow.get(alert.time) < now:
            yield alert.text
            alert.delete_instance()
