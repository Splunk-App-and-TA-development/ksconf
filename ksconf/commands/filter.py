""" SUBCOMMAND:  ksconf filter <CONF>

Usage example:

    ksconf filter default/savedsearches.conf --stanza "My Special Search" -o my-special-search.conf

Future things to support:

 * SED-like rewriting for stanza name or key values.
 * Mini eval/query language for simple data manipulations supporting mixed used of matching modes
   on a case-by-base basis, custom logic (AND,OR,arbitrary groups), projections, and content
   rewriting.  (Should leverage custom 'combine' mini-language where possible.)

"""

from __future__ import absolute_import, unicode_literals

import argparse
import sys
import re

from fnmatch import fnmatch, fnmatchcase

from ksconf.commands import KsconfCmd, dedent, ConfFileType
from ksconf.conf.parser import PARSECONF_MID_NC, write_conf_stream
from ksconf.consts import EXIT_CODE_SUCCESS
from ksconf.util.completers import conf_files_completer


class FilteredList(object):
    IGNORECASE = I = 1

    def __init__(self, match_mode="string", flags=0):
        self.data = []
        self.flags = flags
        self._match = self._set_match_func(match_mode)

    def _set_match_func(self, match_mode):
        if match_mode == "string":
            return self._match_string
        elif match_mode == "regex":
            return self._match_regex
        elif match_mode == "wildcard":
            return self._match_wildcard
        else:
            raise ValueError("Unknown matching mode {!r}".format(match_mode))

    @staticmethod
    def _feed_from_file(path):
        items = []
        with open(path) as f:
            for line in f:
                line = line.rstrip()
                # Skip empty or "comment" lines
                if not line or line[0] == "#":
                    continue
                items.append(line)
        sys.stderr.write("Loaded patterns from {}.  Found {} entries.\n".format(path, len(items)))
        return items

    def feed(self, item):
        if item.startswith("file://"):
            # File ingestion mode
            filename = item[7:]
            self.data.extend(self._feed_from_file(filename))
        else:
            self.data.append(item)

    def match(self, item):
        if self.data:
            return self._match(item)
        else:
            #  No patterns defined.  No filter rule(s) => allow all through
            return True

    @property
    def has_rules(self):
        return len(self.data) > 0

    def _match_string(self, item):
        if self.flags & self.IGNORECASE:

            # Lower-case all strings in self.data.  (Only need to do this once)
            if not getattr(self, "_match_string_lc_fixup", False):
                print("ONE TIME CONVERSTION!")
                self.data = [i.lower() for i in self.data]
                self._match_string_lc_fixup = True
            item = item.lower()
        print('{} in {}  ==> {}'.format(item, self.data, item in self.data))
        return item in self.data

    def _match_regex(self, item):
        re_flags = 0
        if self.flags & self.IGNORECASE:
            re_flags |= re.IGNORECASE
        for pattern in self.data:
            pattern_re = re.compile(pattern, re_flags)
            if pattern_re.match(item):
                return True
        return False

    def _match_wildcard(self, item):
        if self.flags & self.IGNORECASE:
            match = fnmatch
        else:
            match = fnmatchcase
        for pattern in self.data:
            if match(pattern, item):
                return True
        return False




class FilterCmd(KsconfCmd):
    help = "A stanza-aware GREP tool for conf files"
    description = dedent("""
    Filter the contents of a conf file in various ways.  Stanzas can be included
    or excluded based on provided filter, based on the presents or value of a key.

    Where possible, this command supports GREP-like arguments to bring a familiar feel.
    """)

    # format = "manual"
    maturity = "alpha"


    def __init__(self, *args, **kwargs):
        super(FilterCmd, self).__init__(*args, **kwargs)
        self.stanza_filters = None
        self.attr_presence_filters = None

    def register_args(self, parser):
        parser.add_argument("conf", metavar="CONF", help="Input conf file", nargs="+",
                            type=ConfFileType("r", "load", parse_profile=PARSECONF_MID_NC)
                            ).completer = conf_files_completer
        parser.add_argument("-o", "--output", metavar="FILE",
                            type=argparse.FileType('w'), default=self.stdout,
                            help="File where the filtered results are written.  "
                                 "Defaults to standard out.")
        parser.add_argument("--comments", "-C",
                            action="store_true", default=False,
                            help="Preserve comments.  Comments are discarded by default.")

        parser.add_argument("--match", "-m",  # metavar="MODE",
                            choices=["regex", "wildcard", "string"],
                            default="regex",
                            help="""
            Specify pattern matching mode.
            Defaults to 'wildcard' allowing for '*' and  '?' matching.
            Use 'regex' for more power but watch out for shell escaping.
            Use 'string' enable literal matching.""")
        parser.add_argument("--ignore-case", "-i", action="store_true",
                            help="""
            Ignore case when comparing or matching strings.
            By default matches are case-sensitive.""")
        parser.add_argument("--invert-match", "-v", action="store_true",
                            help="""
            Invert match results.
            This can be used to show what content does NOT match,
            or make a backup copy of excluded content.""")


        pg_out = parser.add_argument_group("Output mode", """
            Select an alternate output mode.
            If any of the following options are used, the stanza output is not shown.
            """)
        pg_out.add_argument("--files-with-matches", "-l", action="store_true",
                            help="List files that match the given search criteria")
        pg_out.add_argument("--count", "-c", action="store_true",
                            help="Count matching stanzas")

        pg_sel = parser.add_argument_group("Stanza selection", """
            Include or exclude entire stanzas using these filter options.

            All filter options can be provided multiple times.
            If you have a long list of filters, they can be saved in a file and referenced using
            the special 'file://' prefix.""")

        pg_sel.add_argument("--stanza", metavar="PATTERN", action="append", default=[],
                            help="""
            Match any stanza who's name matches the given pattern.
            PATTERN supports bulk patterns via the 'file://' prefix.""")

        pg_sel.add_argument("--attr-present", metavar="ATTR", action="append", default=[],
                            help="""
            Match any stanza that includes the ATTR attribute.
            ATTR supports bulk attribute patterns via the 'file://' prefix.""")

        pg_sel.add_argument("--attr-eq", metavar=("ATTR", "PATTERN"), nargs=2, action="append",
                            default=[],
                            help="""
            Match any stanza that includes an attribute matching the pattern.
            PATTERN supports the special 'file://filename' syntax.""")

        '''
        pg_sel.add_argument("--attr-ne",  metavar=("ATTR", "PATTERN"), nargs=2, action="append",
                            default=[],
                            help="""
            Match any stanza that includes an attribute matching the pattern.
            PATTERN supports the special 'file://' syntax.""")
        '''

        '''
        pg_con = parser.add_argument_group("Attribute retention","""
            Include or exclude entire stanzas using these options.
            By default all attributes are preserved.""")

        pg_con.add_argument("--filter-attrs", help="When enabled, only the matching attributes "
                                                   "names will be exported."
        '''

    def prep_filters(self, args):
        flags = 0
        if args.ignore_case:
            flags |= FilteredList.IGNORECASE

        self.stanza_filters = FilteredList(args.match, flags)
        for pattern in args.stanza:
            self.stanza_filters.feed(pattern)

        self.attr_presence_filters = FilteredList(args.match, flags)
        for pattern in args.attr_present:
            self.attr_presence_filters.feed(pattern)

    def _test_stanza(self, stanza, attributes):
        if self.stanza_filters.match(stanza):
            # If there are no attribute level filters, automatically keep (preserves empty stanzas)
            if not self.attr_presence_filters.has_rules:
                return True
            # See if any of the attributes we are looking for exist, if so keep the entire stanza
            for attr in attributes:
                if self.attr_presence_filters.match(attr):
                    return True
        return False

    def run(self, args):
        ''' Filter configuration files. '''
        self.prep_filters(args)

        # By allowing mutliple input CONF files, this means that we could have duplicate stanzas (not detected by the parser)
        # so for now that just means duplicate stanzas on the output, but that may be problematic
        # I guess this is really up to the invoker to know if they care about that or not... Still would be helpful for a quick "grep" of a large number of files

        for conf in args.conf:
            conf.set_parser_option(keep_comments=args.comments)
            cfg = conf.data
            # Should this be an ordered dict?
            cfg_out = dict()
            for stanza_name, attributes in cfg.items():
                '''
                keep = self._test_stanza(stanza_name, attributes)
                if args.invert_match:
                    keep = not keep
                '''
                keep = self._test_stanza(stanza_name, attributes) ^ args.invert_match
                if keep:
                    cfg_out[stanza_name] = attributes

            if cfg_out:
                if len(args.conf) > 1:
                    args.output.write("#  {}".format(conf.name))
                write_conf_stream(args.output, cfg_out)

        return EXIT_CODE_SUCCESS