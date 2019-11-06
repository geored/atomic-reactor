"""
Copyright (c) 2015, 2019 Red Hat, Inc
All rights reserved.

This software may be modified and distributed under the terms
of the BSD license. See the LICENSE file for details.
"""

from __future__ import print_function, unicode_literals, absolute_import
import os
import json
import types
from textwrap import dedent

from atomic_reactor.plugins.input_osv3 import OSv3InputPlugin
from osbs.api import OSBS
from tests.constants import REACTOR_CONFIG_MAP
from atomic_reactor.constants import (PLUGIN_BUMP_RELEASE_KEY,
                                      PLUGIN_DISTGIT_FETCH_KEY,
                                      PLUGIN_DOCKERFILE_CONTENT_KEY,
                                      PLUGIN_FETCH_MAVEN_KEY,
                                      PLUGIN_INJECT_PARENT_IMAGE_KEY,
                                      PLUGIN_KOJI_IMPORT_PLUGIN_KEY,
                                      PLUGIN_KOJI_PARENT_KEY,
                                      PLUGIN_KOJI_PROMOTE_PLUGIN_KEY,
                                      PLUGIN_KOJI_TAG_BUILD_KEY,
                                      PLUGIN_KOJI_UPLOAD_PLUGIN_KEY,
                                      PLUGIN_KOJI_DELEGATE_KEY,
                                      PLUGIN_RESOLVE_COMPOSES_KEY,
                                      PLUGIN_SENDMAIL_KEY)
import pytest
from flexmock import flexmock
from jsonschema import ValidationError


class TestOSv3InputPlugin(object):
    """Tests for OSv3InputPlugin"""

    def test_doesnt_fail_if_no_plugins(self):
        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'ATOMIC_REACTOR_PLUGINS': '{}',
        }
        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        assert plugin.run()['openshift_build_selflink'] is None

    @pytest.mark.parametrize('build, expected', [
        ('{"metadata": {"selfLink": "/foo/bar"}}', '/foo/bar'),
        ('{"metadata": {}}', None),
        ('{}', None),
    ])
    def test_sets_selflink(self, build, expected):
        mock_env = {
            'BUILD': build,
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'ATOMIC_REACTOR_PLUGINS': '{}',
        }
        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        assert plugin.run()['openshift_build_selflink'] == expected

    def enable_plugins_configuration(self, plugins_json):
        # flexmock won't mock a non-existent method, so add it if necessary
        try:
            getattr(OSBS, 'render_plugins_configuration')
        except AttributeError:
            setattr(OSBS, 'render_plugins_configuration',
                    types.MethodType(lambda x: x, 'render_plugins_configuration'))
        (flexmock(OSBS)
            .should_receive('render_plugins_configuration')
            .and_return(json.dumps(plugins_json)))

    @pytest.mark.parametrize(('plugins_variable', 'valid'), [
        ('ATOMIC_REACTOR_PLUGINS', True),
        ('USER_PARAMS', True),
        ('DOCK_PLUGINS', False),
    ])
    def test_plugins_variable(self, plugins_variable, valid):
        plugins_json = {
            'postbuild_plugins': [],
        }

        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            plugins_variable: json.dumps(plugins_json),
        }

        if plugins_variable == 'USER_PARAMS':
            mock_env['REACTOR_CONFIG'] = REACTOR_CONFIG_MAP
            self.enable_plugins_configuration(plugins_json)
            mock_env.update({
                plugins_variable: json.dumps({
                    'build_json_dir': 'inputs',
                    'build_type': 'orchestrator',
                    'git_ref': 'test',
                    'git_uri': 'test',
                    'user': 'user'
                }),
            })

        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        if valid:
            assert plugin.run()['postbuild_plugins'] is not None
        else:
            with pytest.raises(RuntimeError):
                plugin.run()

    def test_remove_dockerfile_content(self):
        plugins_json = {
            'prebuild_plugins': [
                {
                    'name': 'before',
                },
                {
                    'name': PLUGIN_DOCKERFILE_CONTENT_KEY,
                },
                {
                    'name': 'after',
                },
            ]
        }

        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'ATOMIC_REACTOR_PLUGINS': json.dumps(plugins_json),
        }
        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        assert plugin.run()['prebuild_plugins'] == [
            {
                'name': 'before',
            },
            {
                'name': 'after',
            },
        ]

    def test_remove_everything(self):
        plugins_json = {
            'build_json_dir': 'inputs',
            'build_type': 'orchestrator',
            'git_ref': 'test',
            'git_uri': 'test',
            'user': 'user',
            'prebuild_plugins': [
                {'name': 'before', },
                {'name': PLUGIN_BUMP_RELEASE_KEY, },
                {'name': PLUGIN_KOJI_DELEGATE_KEY, },
                {'name': PLUGIN_FETCH_MAVEN_KEY, },
                {'name': PLUGIN_DISTGIT_FETCH_KEY, },
                {'name': PLUGIN_DOCKERFILE_CONTENT_KEY, },
                {'name': PLUGIN_INJECT_PARENT_IMAGE_KEY, },
                {'name': PLUGIN_KOJI_PARENT_KEY, },
                {'name': PLUGIN_RESOLVE_COMPOSES_KEY, },
                {'name': 'after', },
            ],
            'postbuild_plugins': [
                {'name': 'before', },
                {'name': PLUGIN_KOJI_UPLOAD_PLUGIN_KEY, },
                {'name': 'after', },
            ],
            'exit_plugins': [
                {'name': 'before', },
                {'name': PLUGIN_KOJI_IMPORT_PLUGIN_KEY, },
                {'name': PLUGIN_KOJI_PROMOTE_PLUGIN_KEY, },
                {'name': PLUGIN_KOJI_TAG_BUILD_KEY, },
                {'name': PLUGIN_SENDMAIL_KEY, },
                {'name': 'after', },
            ]
        }
        minimal_config = dedent("""\
            version: 1
        """)

        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'USER_PARAMS': json.dumps(plugins_json),
            'REACTOR_CONFIG': minimal_config
        }
        flexmock(os, environ=mock_env)
        self.enable_plugins_configuration(plugins_json)

        plugin = OSv3InputPlugin()
        plugins = plugin.run()
        for phase in ('prebuild_plugins', 'postbuild_plugins', 'exit_plugins'):
            assert plugins[phase] == [
                {'name': 'before', },
                {'name': 'after', },
            ]

    @pytest.mark.parametrize(('override', 'valid'), [
        ('invalid_override', False),
        ({'version': 1}, True),
        (None, True),
    ])
    @pytest.mark.parametrize('buildtype', [
        'worker', 'orchestrator'
    ])
    def test_validate_reactor_config_override(self, override, valid, buildtype):
        plugins_json = {
            'postbuild_plugins': [],
        }

        user_params = {
            'build_json_dir': 'inputs',
            'build_type': buildtype,
            'git_ref': 'test',
            'git_uri': 'test',
            'user': 'user',
            'reactor_config_map': REACTOR_CONFIG_MAP,
        }
        if override:
            user_params['reactor_config_override'] = override
        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'REACTOR_CONFIG': REACTOR_CONFIG_MAP,
            'USER_PARAMS': json.dumps(user_params)
        }

        self.enable_plugins_configuration(plugins_json)

        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        if valid:
            plugin.run()
        else:
            with pytest.raises(ValidationError):
                plugin.run()

    @pytest.mark.parametrize('plugins_type', ['prebuild_plugins',
                                              'buildstep_plugins',
                                              'postbuild_plugins',
                                              'prepublish_plugins',
                                              'exit_plugins'
                                              ])
    def test_fails_on_invalid_plugin_request(self, plugins_type):
        # no name plugin request
        plugins_json = {plugins_type: [{'args': {}}, {'name': 'foobar'}]},

        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'ATOMIC_REACTOR_PLUGINS': json.dumps(plugins_json),
        }
        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        with pytest.raises(ValidationError):
            plugin.run()

    @pytest.mark.parametrize(('arrangement_version', 'valid'), [
        (1, False),
        (2, False),
        (3, False),
        (4, False),
        (5, False),
        (6, True),
    ])
    @pytest.mark.parametrize('buildtype', [
        'worker', 'orchestrator'
    ])
    def test_arrangement_version(self, arrangement_version, valid, buildtype):
        plugins_json = {
            'postbuild_plugins': [],
        }

        user_params = {
            'arrangement_version': arrangement_version,
            'build_json_dir': 'inputs',
            'build_type': buildtype,
            'git_ref': 'test',
            'git_uri': 'test',
            'user': 'user',
            'reactor_config_map': REACTOR_CONFIG_MAP,
        }
        mock_env = {
            'BUILD': '{}',
            'SOURCE_URI': 'https://github.com/foo/bar.git',
            'SOURCE_REF': 'master',
            'OUTPUT_IMAGE': 'asdf:fdsa',
            'OUTPUT_REGISTRY': 'localhost:5000',
            'REACTOR_CONFIG': REACTOR_CONFIG_MAP,
            'USER_PARAMS': json.dumps(user_params)
        }

        self.enable_plugins_configuration(plugins_json)

        flexmock(os, environ=mock_env)

        plugin = OSv3InputPlugin()
        if valid:
            plugin.run()
        else:
            with pytest.raises(ValueError):
                plugin.run()
