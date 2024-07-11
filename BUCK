# Copyright 2024. WebPros International GmbH. All rights reserved.
# vim:ft=python:

include_defs('//product.defs.py')


python_binary(
    name = 'cloudlinux7to8.pex',
    platform = 'py3',
    build_args = ['--python-shebang', '/usr/bin/env python3'],
    main_module = 'cloudlinux7to8.main',
    deps = [
        'dist-upgrader//pleskdistup:lib',
        '//cloudlinux7to8:lib',
    ],
)

genrule(
    name = 'cloudlinux7to8',
    srcs = [':cloudlinux7to8.pex'],
    out = 'cloudlinux7to8',
    cmd = 'cp $(location :cloudlinux7to8.pex) $OUT && chmod +x $OUT',
)
