# Copyright 2024. WebPros International GmbH. All rights reserved.
# vim:ft=python:

PRODUCT_VERSION = '1.3.1'

genrule(
    name = 'version',
    out = 'version.json',
    bash = r"""echo "{\"version\": \"%s\", \"revision\": \"`git rev-parse HEAD`\"}" > $OUT""" % (PRODUCT_VERSION),
)


python_binary(
    name = 'cloudlinux7to8.pex',
    platform = 'py3',
    build_args = ['--python-shebang', '/usr/bin/env python3'],
    main_module = 'cloudlinux7to8converter.main',
    deps = [
        'dist-upgrader//pleskdistup:lib',
        '//cloudlinux7to8converter:lib',
    ],
)

genrule(
    name = 'cloudlinux7to8',
    srcs = [':cloudlinux7to8.pex'],
    out = 'cloudlinux7to8',
    cmd = 'cp $(location :cloudlinux7to8.pex) $OUT && chmod +x $OUT',
)
