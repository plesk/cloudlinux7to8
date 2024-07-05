# Copyright 2024. WebPros International GmbH. All rights reserved.
# vim:ft=python:

include_defs('//product.defs.py')


python_binary(
    name = 'cloudlinux7to8.pex',
    platform = 'py3',
    # libgcc_s.so.1 is preloaded to workaround crash due to "libgcc_s.so.1 must
    # be installed for pthread_cancel to work" instead of clean exit after
    # dist-upgrade, see https://bugs.python.org/issue44434
    build_args = ['--python-shebang', '/usr/bin/env -S LD_PRELOAD=libgcc_s.so.1 python3'],
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
