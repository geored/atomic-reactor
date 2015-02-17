"""
Script for building docker image. This is expected to run inside container.
"""

import json
import logging
import shutil
import tempfile

from dock.build import InsideBuilder
from dock.plugin import PostBuildPluginsRunner, PreBuildPluginsRunner, InputPluginsRunner


logger = logging.getLogger(__name__)


class BuildResults(object):
    build_logs = None
    dockerfile = None
    built_img_inspect = None
    built_img_info = None
    base_img_inspect = None
    base_img_info = None
    base_plugins_output = None
    built_img_plugins_output = None
    container_id = None
    return_code = None


class BuildResultsEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, BuildResults):
            return {
                'build_logs': obj.build_logs,
                'built_img_inspect': obj.built_img_inspect,
                'built_img_info': obj.built_img_info,
                'base_img_info': obj.base_img_info,
                'base_plugins_output': obj.base_plugins_output,
                'built_img_plugins_output': obj.built_img_plugins_output,
            }
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)


class BuildResultsJSONDecoder(json.JSONDecoder):
    def decode(self, obj):
        d = super(BuildResultsJSONDecoder, self).decode(obj)
        results = BuildResults()
        results.built_img_inspect = d.get('built_img_inspect', None)
        results.built_img_info = d.get('built_img_info', None)
        results.base_img_info = d.get('base_img_info', None)
        results.base_plugins_output = d.get('base_plugins_output', None)
        results.built_img_plugins_output = d.get('built_img_plugins_output', None)
        return results


class DockerBuildWorkflow(object):
    """
    This class defines a workflow for building images:

    1. pull image from registry
    2. tag it properly if needed
    3. clone git repo
    4. build image
    5. tag it
    6. push it to registries
    """

    def __init__(self, git_url, image, git_dockerfile_path=None,
                 git_commit=None, parent_registry=None, target_registries=None,
                 prebuild_plugins=None, postbuild_plugins=None, plugin_files=None, **kwargs):
        """
        :param git_url: str, URL to git repo
        :param image: str, tag for built image ([registry/]image_name[:tag])
        :param git_dockerfile_path: str, path to dockerfile within git repo (if not in root)
        :param git_commit: str, git commit to check out
        :param parent_registry: str, registry to pull base image from
        :param target_registries: list of str, list of registries to push image to (might change in future)
        :param prebuild_plugins: dict, arguments for pre-build plugins
        :param postbuild_plugins: dict, arguments for post-build plugins
        :param plugin_files: list of str, load plugins also from these files
        """
        self.git_url = git_url
        self.image = image
        self.git_dockerfile_path = git_dockerfile_path
        self.git_commit = git_commit
        self.parent_registry = parent_registry
        self.target_registries = target_registries

        self.prebuild_plugins_conf = prebuild_plugins
        self.postbuild_plugins_conf = postbuild_plugins
        self.prebuild_results = {}
        self.postbuild_results = {}
        self.plugin_files = plugin_files

        self.kwargs = kwargs

        self.builder = None
        self.build_logs = None

        self.repos = {}  # this should be filled by plugins

    def build_docker_image(self):
        """
        build docker image

        :return: BuildResults
        """
        tmpdir = tempfile.mkdtemp()
        self.builder = InsideBuilder(self.git_url, self.image, git_dockerfile_path=self.git_dockerfile_path,
                                     git_commit=self.git_commit, tmpdir=tmpdir)
        try:
            if self.parent_registry:
                self.builder.pull_base_image(self.parent_registry)

            # time to run pre-build plugins, so they can access cloned repo,
            # base image
            logger.info("running pre-build plugins")
            prebuild_runner = PreBuildPluginsRunner(self.builder.tasker, self, self.prebuild_plugins_conf,
                                                    plugin_files=self.plugin_files)
            prebuild_runner.run()

            image = self.builder.build()
            # TODO: in case of docker host build, remove image
            self.build_logs = self.builder.last_logs[:]
            if image:
                if self.target_registries:
                    for target_registry in self.target_registries:
                        self.builder.push_built_image(target_registry)

            postbuild_runner = PostBuildPluginsRunner(self.builder.tasker, self, self.postbuild_plugins_conf,
                                                      plugin_files=self.plugin_files)
            postbuild_runner.run()
            return image
        finally:
            shutil.rmtree(tmpdir)

    def _prepare_response(self):
        """
        prepare response for build: gather info about images

        :return BuildResults
        """
        # FIXME: everything in here should be in separate postbuild plugin
        assert self.builder is not None
        runner = PostBuildPluginsRunner(self.builder.tasker)
        results = BuildResults()
        results.built_img_inspect = self.builder.inspect_built_image()
        results.built_img_info = self.builder.get_built_image_info()
        results.base_img_inspect = self.builder.inspect_base_image()
        results.base_img_info = self.builder.get_base_image_info()
        results.base_plugins_output = runner.run(self.builder.base_image_name)
        results.built_img_plugins_output = runner.run(self.builder.image)
        return results


def build_inside(input, input_args=None):
    """
    use requested input plugin to load configuration and then initiate build
    """
    if not input:
        raise RuntimeError("No input method specified!")
    else:
        logger.debug("getting build json from input %s", input)

        input_args = input_args or []
        cleaned_input_args = {}
        for arg in input_args:
            key, value = arg.split("=", 1)
            cleaned_input_args[key] = value

        input_runner = InputPluginsRunner([{'name': input, 'args': cleaned_input_args}])
        build_json = input_runner.run()[input]
    if not build_json:
        raise RuntimeError("No valid build json!")
    # TODO: validate json
    dbw = DockerBuildWorkflow(**build_json)
    image = dbw.build_docker_image()
    if not image:
        raise RuntimeError("no image built")
