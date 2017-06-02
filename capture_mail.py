#!/usr/bin/env python3

"""\
標準入力に与えられるメールに関するデータを取得し、
実行時のプロセスの環境変数等と併せてINFOレベルのログにダンプする。
また標準出力に対して RFC 3463 に基づいたエラーメッセージを出力し、
プロセス自身はエラー終了する。

例えば /etc/aliases に次のように記述することで使用する。MTAはPostfixが前提。

capture:  "|/path/to/capture.py /tmp/capture.log"
"""

from argparse import ArgumentParser, RawDescriptionHelpFormatter
import email.parser
import grp
import locale
from logging import (
    getLogger, Formatter, StreamHandler, FileHandler, INFO, DEBUG
)
from logging.handlers import SysLogHandler
import os
import platform
import pwd
import sys
import traceback


def dump_system_info_to_logger(logger, *, log_level=DEBUG):
    logger.log(log_level, 'Showing system-info:')
    detailed_version_str = ' '.join(sys.version.split('\n'))
    logger.log(log_level, '- Python Version:      {} ({})'
               .format(platform.python_version(), detailed_version_str))
    logger.log(log_level, '- platform.platform(): {}'
               .format(platform.platform()))
    logger.log(log_level, '- os.getcwd():    {}'.format(os.getcwd()))
    logger.log(log_level, '- os.getuid():    {} ({})'
               .format(os.getuid(), pwd.getpwuid(os.getuid())[0]))
    logger.log(log_level, '- os.geteuid():   {} ({})'
               .format(os.geteuid(), pwd.getpwuid(os.geteuid())[0]))
    logger.log(log_level, '- os.getgid():    {} ({})'
               .format(os.getgid(), grp.getgrgid(os.getgid())[0]))
    logger.log(log_level, '- os.getegid():   {} ({})'
               .format(os.getegid(), grp.getgrgid(os.getegid())[0]))
    # 'ANSI_X3.4-1968' == 'us-ascii'
    # local(8) から呼び出される際、open()のデフォルトエンコーディングが
    # locale.getpreferredencoding(False) で指定された文字列になるのだが、
    # それが ANSI_X3.4-1968 (つまりASCII) となる。
    # 以下のINFOログではそのことを確認する。
    logger.log(log_level, '- sys.getdefaultencoding(): {}'
               .format(sys.getdefaultencoding()))
    logger.log(log_level, '- sys.stdin.encoding:       {}'
               .format(sys.stdin.encoding))
    logger.log(log_level, '- sys.stdout.encoding:      {}'
               .format(sys.stdout.encoding))
    logger.log(log_level, '- locale.getpreferredencoding(False): {}'
               .format(locale.getpreferredencoding(False)))


def dump_env_variables_to_logger(logger, *, log_level=DEBUG):
    logger.log(log_level, 'Showing environment variables:')
    for k, v in os.environ.items():
        logger.log(log_level, '- "{}" -> "{}"'.format(k, v))


def dump_email_header_to_logger(msg, logger, *, log_level=DEBUG, prefix=''):
    logger.log(log_level, '{}Header:'.format(prefix))
    keys = msg.keys()
    # Received等重複するキーがある
    for key in sorted(set(keys), key=keys.index):
        lst = msg.get_all(key)
        if len(lst) > 1:
            logger.log(log_level, ('{}- {} ({} items):'
                                   .format(prefix, key, len(lst))))
            indent_size = len(str(len(lst) - 1))
            for i, elem in enumerate(lst):
                # 次のように表示される (例えばReceived ヘッダで使用される)
                # - 1:
                # - >>
                # - >>
                for j, line in enumerate(elem.split('\n')):
                    if j == 0:
                        s = '{}- {{:{}<}}: {{}}'.format(prefix, indent_size)
                        logger.log(log_level, s.format(i, line.rstrip()))
                    else:
                        s = '{}. {} {{}}'.format(prefix,
                                                 '>' * (indent_size + 1))
                        logger.log(log_level, s.format(line.rstrip()))
        else:
            elem = lst[0]
            lines = elem.split('\n')
            if len(lines) > 1:
                logger.log(log_level, '{}- {}:'.format(prefix, key))
                for i, line in enumerate(lines):
                    if i == 0:
                        logger.log(log_level, '{}-- {}'.format(prefix,
                                                               line.rstrip()))
                    else:
                        logger.log(log_level, '{}.. {}'.format(prefix,
                                                               line.rstrip()))
            else:
                logger.log(log_level, '{}- {}: {}'.format(prefix,
                                                          key, elem.rstrip()))


def dump_email_body_to_logger(msg, logger,
                              *,
                              log_level=DEBUG,
                              message_index='0',
                              prefix='',
                              indent_str='  '):
    # 「charset」には二通りの意味があり得る。
    #
    # 1) quoted-printableやbase64に関するもの
    # 2) 文字列のエンコーディングに関するもの (UTF-8等)
    #
    # msg.get_payload(decode=True)の「decode」は前者に関する処理で、
    # 既存のメッセージを必要であればデコードして
    # bytesに変換することを意味する。この際の「charset」は
    # msg.get_charset()で得られるが、ここでは使用する必要がない
    #
    # 2)に関する処理はContent-Typeのパラメータから得られる
    # 「charset」を使用する(e.g. 'text/html; charset=UTF-8' -> 'UTF-8')
    #
    encoding = msg.get_param('charset')
    logger.log(log_level,
               ('{}Message content {}'
                ' (content_type: {}, params: {}, charset: {}, encoding: {}):'
                .format(prefix,
                        message_index,
                        msg.get_content_type(),
                        msg.get_params(),
                        msg.get_charset(),
                        encoding)))
    if not encoding:
        encoding = 'us-ascii'
    if msg.preamble:
        logger.log(log_level, '{}preample:'.format(prefix))
        for line in msg.preamble.split('\n'):
            logger.log(log_level, '{}> {}'.format(prefix, line.rstrip()))
    if msg.is_multipart():
        for i, sub_msg in enumerate(msg.get_payload()):
            new_prefix = prefix + indent_str
            new_message_index = '{}-{}'.format(message_index, i + 1)
            dump_email_body_to_logger(sub_msg,
                                      logger,
                                      message_index=new_message_index,
                                      log_level=log_level,
                                      prefix=new_prefix)
    else:
        if msg.get_content_maintype() == 'text':
            text = msg.get_payload(decode=True).decode(encoding)
            for line in text.split('\n'):
                logger.log(log_level, '{}> {}'.format(prefix, line.rstrip()))
        else:
            data = msg.get_payload(decode=True)
            logger.log(log_level, '{}> (Possibly binary data with size {})'
                       .format(prefix, len(data)))
    if msg.epilogue:
        logger.log(log_level, '{}epilogue:'.fromat(prefix))
        for line in msg.epilogue.split('\n'):
            logger.log(log_level, '{}> {}'.format(prefix, line.rstrip()))
    if msg.defects:
        logger.log(log_level, '{}defects:'.format(prefix))
        for defect in msg.defects:
            logger.log(log_level, '{}- {} (detail: {})'
                       .format(prefix,
                               defect.__class__.__name__,
                               defect))


def dump_email_to_logger(msg, logger,
                         *,
                         log_level=DEBUG,
                         prefix='',
                         indent_str='  '):
    """\
    msgのヘッダと本体をloggerに出力する。
    マルチパートのメッセージではネストする毎に
    indent_strがprefixに追加されながら再起的にこの関数が呼び出される
    """
    dump_email_header_to_logger(msg, logger,
                                log_level=log_level, prefix=prefix)
    dump_email_body_to_logger(msg, logger,
                              log_level=log_level,
                              message_index='0',
                              prefix=prefix,
                              indent_str=indent_str)


def capture_mail(args, logger):
    dump_system_info_to_logger(logger, log_level=INFO)
    dump_env_variables_to_logger(logger, log_level=INFO)

    out_file = None
    try:
        if args.out_file:
            out_file = open(args.out_file, 'w')
        # 標準入力をそのまま出力し、それをEmailメッセージとしてパーサに与える。
        parser = email.parser.FeedParser()
        logger.info('stdin:')
        for line in sys.stdin:
            if out_file:
                out_file.write(line)
            parser.feed(line)
            logger.info('>>> {}'.format(line.rstrip()))
        msg = parser.close()
        dump_email_to_logger(msg, logger, log_level=INFO)
    except Exception as e:
        logger.error('Exception raised during handling stdin ({}, {}'
                     .format(e.__class__.__name__, e))
        for line in traceback.format_exc().rstrip().split('\n'):
            logger.error(line)
    finally:
        if out_file:
            try:
                out_file.close()
            except Exception as e:
                logger.error('Exception raised during closing out_File ({}, {}'
                             .format(e.__class__.__name__, e))
                for line in traceback.format_exc().rstrip().split('\n'):
                    logger.error(line)

    if args.do_bounce:
        # ref. RFC 3463
        sys.stderr.write('5.999.999 Testing Error Message\n')
        return 1
    else:
        return 0


def main():
    parser = ArgumentParser(description=(__doc__),
                            formatter_class=RawDescriptionHelpFormatter)
    parser.add_argument('log_file', nargs='?',
                        help=('Path to log file. If unspecified, local '
                              'syslog will be used via /dev/log.'
                              'If "-" is specified, stderr will be used.'))
    parser.add_argument('-b', '--do-bounce', action='store_true',
                        help='Bounce back the mail when true')
    parser.add_argument('-o', '--out-file',
                        help='Store input content to the specified file.')
    parser.add_argument('-e', '--encoding', default='UTF-8',
                        help='Log encoding')
    parser.add_argument('-d', '--debug', action='store_true',
                        help='Show debug log')
    args = parser.parse_args()

    logger = getLogger(__name__)
    is_syslog = False
    if not args.log_file:
        handler = SysLogHandler('/dev/log')
        is_syslog = True
    elif args.log_file == '-':
        handler = StreamHandler()
    else:
        handler = FileHandler(args.log_file, encoding=args.encoding)

    if args.debug:
        log_level = DEBUG
    else:
        log_level = INFO
    logger.setLevel(log_level)
    logger.addHandler(handler)
    handler.setLevel(log_level)
    if is_syslog:
        handler.setFormatter(Formatter('%(levelname)7s %(message)s'))
    else:
        handler.setFormatter(
            Formatter('%(asctime)s %(levelname)7s %(message)s'))

    logger.info('Start running (with Python {})'
                .format(platform.python_version()))
    exit_status = capture_mail(args, logger)
    logger.info('Finished running with exit status ({})'.format(exit_status))
    return exit_status


if __name__ == '__main__':
    sys.exit(main())
