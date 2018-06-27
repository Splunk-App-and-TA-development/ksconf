"""
SUBCOMMAND:  ksconf merge --target=<CONF> <CONF> [ <CONF-n> ... ]

Usage example:

    ksconf merge --target=master-props.conf /opt/splunk/etc/apps/*TA*/{default,local}/props.conf

"""
from __future__ import absolute_import
from __future__ import unicode_literals
from ksconf.conf.merge import merge_conf_files
from ksconf.consts import EXIT_CODE_SUCCESS
from ksconf.conf.parser import PARSECONF_STRICT, PARSECONF_MID
from ksconf.commands import KsconfCmd, dedent, ConfFileProxy, ConfFileType
from ksconf.util.completers import conf_files_completer



class MergeCmd(KsconfCmd):
    help = "Merge two or more .conf files"
    description = dedent("""\
    Merge two or more .conf files into a single combined .conf file.

    This could be used to merge the props.conf file from ALL technology addons into a single file:

    ksconf merge --target=master-props.conf etc/apps/*TA*/{default,local}/props.conf
    """)
    format = "manual"

    def register_args(self, parser):
        parser.add_argument("conf", metavar="FILE", nargs="+",
                             type=ConfFileType("r", "load", parse_profile=PARSECONF_MID),
                             help="The source configuration file to pull changes from."
                             ).completer = conf_files_completer
        parser.add_argument("--target", "-t", metavar="FILE",
                             type=ConfFileType("r+", "none", parse_profile=PARSECONF_STRICT),
                             default=ConfFileProxy("<stdout>", "w", self.stdout),
                             help="Save the merged configuration files to this target file.  If not "
                                  "given, the default is to write the merged conf to standard output."
                             ).completer = conf_files_completer
        parser.add_argument("--dry-run", "-D", default=False, action="store_true",
                             help="Enable dry-run mode.  Instead of writing to TARGET, show what "
                                  "changes would be made to it in the form of a 'diff'. "
                                  "If TARGET doesn't exist, then show the merged file.")
        parser.add_argument("--banner", "-b", default="",
                             help="A banner or warning comment to add to the TARGET file.  Often used "
                                  "to warn Splunk admins from editing a auto-generated file.")

    def run(self, args):
        ''' Merge multiple configuration files into one '''
        merge_conf_files(args.target, args.conf, dry_run=args.dry_run, banner_comment=args.banner)
        return EXIT_CODE_SUCCESS
