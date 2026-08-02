"""Pin the mapping from command-line format flags to internal format values.

The README and CLAUDE.md have disagreed about what `-S` means (issue #77). These tests
make the argument parser the arbiter, so the two documents cannot drift apart again
without a test failing.

`docs/OUTPUT_FORMATS.md` is the normative spec for what each format then emits.
"""

import pytest
from unittest.mock import patch

from ssky.main import parse


def parse_argv(*argv):
    """Run the real argument parser over argv and return (subcommand, args)."""
    with patch('sys.argv', ['ssky', *argv]):
        return parse()


@pytest.mark.parametrize('flag,expected', [
    ('-I', 'id'),
    ('--id', 'id'),
    ('-J', 'json'),
    ('--json', 'json'),
    ('-L', 'long'),
    ('--long', 'long'),
    ('-S', 'simple_json'),
    ('--simple-json', 'simple_json'),
    ('-T', 'text'),
    ('--text', 'text'),
])
def test_format_flag_maps_to_expected_format(flag, expected):
    _, args = parse_argv('get', flag)
    assert args.format == expected


def test_no_flag_means_short():
    """Short is the unflagged default; it has no flag of its own."""
    _, args = parse_argv('get')
    assert args.format == ''


def test_simple_json_is_not_short():
    """Guards the specific error in the README: `-S` is Simple JSON, not Short."""
    _, short = parse_argv('get')
    _, simple_json = parse_argv('get', '-S')
    assert simple_json.format == 'simple_json'
    assert simple_json.format != short.format


@pytest.mark.parametrize('subcommand,extra', [
    ('get', []),
    ('search', ['query']),
    ('user', ['query']),
    ('profile', ['someone.bsky.social']),
    ('post', ['message']),
    ('delete', ['at://did:plc:test/app.bsky.feed.post/abc']),
    ('follow', ['someone.bsky.social']),
    ('unfollow', ['someone.bsky.social']),
    ('repost', ['at://did:plc:test/app.bsky.feed.post/abc']),
    ('unrepost', ['at://did:plc:test/app.bsky.feed.post/abc']),
    ('login', []),
])
def test_every_subcommand_accepts_the_same_format_flags(subcommand, extra):
    """The format options are a shared parent parser, so the set must not vary."""
    for flag, expected in [('-I', 'id'), ('-J', 'json'), ('-L', 'long'),
                           ('-S', 'simple_json'), ('-T', 'text')]:
        _, args = parse_argv(subcommand, *extra, flag)
        assert args.format == expected, f'{subcommand} {flag}'


def test_format_flags_are_mutually_exclusive():
    with pytest.raises(SystemExit):
        parse_argv('get', '-I', '-J')


def test_delimiter_defaults_to_a_single_space():
    _, args = parse_argv('get')
    assert args.delimiter == ' '


def test_output_defaults_to_none():
    _, args = parse_argv('get')
    assert args.output is None
