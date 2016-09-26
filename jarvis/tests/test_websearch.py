#!/usr/bin/env python3
"""Test jarvis.websearch module."""

###############################################################################
# Module Imports
###############################################################################


from jarvis import lex
from jarvis.tests.utils import run


###############################################################################


def test_wikipedia_simple():
    assert run('.w music') == lex.wikipedia.result(title='Music')


def test_wikipedia_ambiguous():
    assert run('.w mercury') == lex.options


def test_wikipedia_not_found():
    assert run('.w sdfgdhfghe') == lex.wikipedia.not_found


###############################################################################


def test_youtube_search_simple():
    assert run('.y I like trains') == lex.youtube.result(
        video_id='hHkKJfcBXcw')


def test_youtube_mssing_likes():
    assert (
        run('https://www.youtube.com/watch?v=llIAae61QHk') ==
        lex.youtube.result(title='Защитники - Официальный тизер!'))


###############################################################################


def test_translate_simple():
    assert (
        run('.trans en-ru teapot') == lex.translate.result(text=['чайничек']))


def test_translate_detect_language():
    assert run('.trans en белочки') == lex.translate.result(text=['squirrels'])


def test_translate_garbage_text():
    assert run('.trans en-ru gsjdhfgsjld') == lex.translate.result


def test_translate_garbage_lang():
    assert run('.trans 1011-en text in robot language') == lex.translate.error


###############################################################################


def test_imdb_simple():
    assert run('.imdb watchmen') == lex.imdb.result(imdbid='tt0409459')


def test_imdb_year():
    assert (
        run('.imdb avengers -y 2015') ==
        lex.imdb.result(title='Avengers: Age of Ultron'))


def test_imdb_search():
    assert run('.imdb -s avengers') == lex.options


def test_imdb_not_found():
    assert run('.imdb whatever -y 2100') == lex.imdb.not_found


###############################################################################


def test_twitter_lookup_simple():
    assert (
        run('https://twitter.com/MeetAnimals/status/778453962970107904') ==
        lex.twitter_lookup(name='Animal Life'))