""" OGC Plugin for interacting with Juju
"""

# pylint: disable=too-many-locals
import os
import tempfile
import uuid
from pathlib import Path

import sh
from ogc.exceptions import SpecConfigException, SpecProcessException
from ogc.run import cmd_ok
from ogc.spec import SpecPlugin
from ogc.state import app

__plugin_name__ = "ogc-plugins-juju"
__version__ = "1.0.35"
__author__ = "Adam Stokes"
__author_email__ = "adam.stokes@gmail.com"
__maintainer__ = "Adam Stokes"
__maintainer_email__ = "adam.stokes@gmail.com"
__description__ = "ogc-plugins-juju, a ogc plugin for working with juju"
__git_repo__ = "https://github.com/battlemidget/ogc-plugins-juju"
__example__ = """
meta:
  name: Validate Charmed Kubernetes
  description: |
    Runs validation test suite against a vanilla deployment of Charmed Kubernetes

plan:
  - &BASE_JOB
    env:
      - SNAP_VERSION=1.16/edge
      - JUJU_DEPLOY_BUNDLE=cs:~containers/charmed-kubernetes
      - JUJU_DEPLOY_CHANNEL=edge
      - JUJU_CLOUD=aws/us-east-2
      - JUJU_CONTROLLER=validate-ck
      - JUJU_MODEL=validate-model
    install:
      - pip install -rrequirements.txt
      - pip install -rrequirements_test.txt
      - pip install git+https://github.com/juju/juju-crashdump.git
      - sudo apt install -qyf build-essential
      - sudo snap install charm --edge --classic
      - sudo snap install juju --classic
      - sudo snap install aws-cli --classic
    before-script:
      - juju:
          cloud: $JUJU_CLOUD
          controller: $JUJU_CONTROLLER
          model: $JUJU_MODEL
          bootstrap:
            debug: no
            replace-controller: yes
            model-default:
              - test-mode=true
          deploy:
            reuse: yes
            bundle: $JUJU_DEPLOY_BUNDLE
            overlay: |
              applications:
                kubernetes-master:
                  options:
                    channel: $SNAP_VERSION
                kubernetes-worker:
                  options:
                    channel: $SNAP_VERSION
            wait: yes
            timeout: 7200
            channel: $JUJU_DEPLOY_CHANNEL
    script:
      - |
        #!/bin/bash
        set -eux
        pytest jobs/integration/validation.py \
             --cloud $JUJU_CLOUD \
             --controller $JUJU_CONTROLLER \
             --model $JUJU_MODEL
    after-script:
      - juju-crashdump -a debug-layer -a config -m $JUJU_CONTROLLER:$JUJU_MODEL
      - juju destroy-controller -y --destroy-all-models --destroy-storage $JUJU_CONTROLLER
"""


class Juju(SpecPlugin):
    """ OGC Juju Plugin
    """

    friendly_name = "OGC Juju Plugin"

    options = [
        {
            "key": "cloud",
            "required": True,
            "description": "Name of one of the support Juju clouds to use.",
        },
        {
            "key": "controller",
            "required": True,
            "description": "Name of the controller to create with Juju.",
        },
        {
            "key": "model",
            "required": True,
            "description": "Name of the model to create with Juju.",
        },
        {
            "key": "force",
            "required": False,
            "description": "Pass in force flag for various components like bootstrap series",
        },
        {
            "key": "bootstrap.constraints",
            "required": False,
            "description": "Juju bootstrap constraints",
        },
        {
            "key": "bootstrap.config",
            "required": False,
            "description": "Juju bootstrap config options",
        },
        {
            "key": "bootstrap.model-default",
            "required": False,
            "description": "Juju bootstrap model defaults",
        },
        {
            "key": "bootstrap.debug",
            "required": False,
            "description": "Turn on debugging during a bootstrap",
        },
        {
            "key": "bootstrap.run",
            "required": False,
            "description": "Pass in a script blob to run in place of the builtin juju bootstrap commands ",
        },
        {
            "key": "bootstrap.disable-add-model",
            "required": False,
            "description": "Do not immediately add a Juju model after bootstrap. Useful if juju model configuration needs to be performed.",
        },
        {
            "key": "bootstrap.replace-controller",
            "required": False,
            "description": "If previous juju controller exists, destroy that and re-bootstrap",
        },
        {
            "key": "bootstrap.series",
            "required": False,
            "description": "Set the OS series to bootstrap with (ie. focal, bionic, xenial)",
        },
        {"key": "deploy", "required": False, "description": "Juju deploy options"},
        {
            "key": "deploy.reuse",
            "required": False,
            "description": "Reuse an existing Juju model, please note that if applications exist and you deploy the same application it will create additional machines.",
        },
        {
            "key": "deploy.bundle",
            "required": True,
            "description": "The Juju bundle to use",
        },
        {
            "key": "deploy.charm",
            "required": False,
            "description": "The Juju charm to use",
        },
        {
            "key": "deploy.overlay",
            "required": False,
            "description": "Juju bundle fragments that can be overlayed a base bundle.",
        },
        {
            "key": "deploy.series",
            "required": False,
            "description": "Set the OS series to deploy applications on (ie. focal, bionic, xenial)",
        },
        {
            "key": "deploy.channel",
            "required": True,
            "description": "Juju channel to deploy from.",
        },
        {
            "key": "deploy.constraints",
            "required": False,
            "description": "Juju deploy model constraints",
        },
        {
            "key": "deploy.wait",
            "required": False,
            "description": "Juju deploy is asynchronous. Turn this option on to wait for a deployment to settle.",
        },
        {
            "key": "deploy.timeout",
            "required": False,
            "description": "How long in seconds to wait for a juju deployment to complete.",
        },
        {
            "key": "config",
            "required": False,
            "description": "Juju charm config options",
        },
    ]

    def __str__(self):
        return "OGC Juju plugin for bootstrap, deployment, testing"

    def _make_executable(self, path):
        mode = os.stat(str(path)).st_mode
        mode |= (mode & 0o444) >> 2
        os.chmod(str(path), mode)

    @property
    def _tempfile(self):
        return tempfile.mkstemp()

    def _run(self, script_data):
        tmp_script = self._tempfile
        tmp_script_path = Path(tmp_script[-1])
        tmp_script_path.write_text(script_data, encoding="utf8")
        self._make_executable(tmp_script_path)
        os.close(tmp_script[0])
        try:
            for line in sh.env(
                str(tmp_script_path), _env=app.env.copy(), _iter=True, _bg_exc=False
            ):
                app.log.debug(f"run :: {line.strip()}")
        except sh.ErrorReturnCode as error:
            raise SpecProcessException(
                f"Failure to bootstrap: {error.stderr.decode().strip()}"
            )

    @property
    def juju(self):
        """ Juju baked command containing the applications environment
        """
        return sh.juju.bake(_env=app.env.copy())

    @property
    def charm(self):
        """ Charm command baked with application environment
        """
        return sh.charm.bake(_env=app.env.copy())

    @property
    def juju_wait(self):
        """ Charm command baked with application environment
        """
        return sh.juju_wait.bake(_env=app.env.copy())

    def juju_ssh(self, target, cmd):
        """ Run ssh command on target
        """
        ssh_opts = "-t -o ControlPath=~/.ssh/master-$$ -o ControlMaster=auto -o ControlPersist=60"
        sh.juju(
            "-m", self._fmt_controller_model, "--pty=True", target, ssh_opts, "--", cmd
        )

    @property
    def _fmt_controller_model(self):
        return (
            f"{self.get_plugin_option('controller')}:{self.get_plugin_option('model')}"
        )

    def _deploy(self):
        """ Handles juju deploy
        """
        bundle = self.opt("deploy.bundle")
        charm = self.opt("deploy.charm")
        overlay = self.opt("deploy.overlay")
        channel = self.opt("deploy.channel")
        constraints = self.opt("deploy.constraints")
        series = self.opt("deploy.series")
        force = self.opt("force")

        deploy_cmd_args = []
        charm_pull_args = []
        if charm:
            deploy_cmd_args = ["-m", self._fmt_controller_model, charm]

        elif bundle and bundle.startswith("cs:"):
            charm_pull_args.append(bundle)
            tmpsuffix = str(uuid.uuid4()).split("-").pop()
            charm_pull_path = f"{tempfile.gettempdir()}/{tmpsuffix}"

            if channel:
                charm_pull_args.append("--channel")
                charm_pull_args.append(channel)
                charm_pull_args.append(charm_pull_path)

            # Access charmstore bundle
            app.log.debug(f"Charm pull: {charm_pull_args}")
            self.charm.pull(*charm_pull_args)
            deploy_cmd_args = [
                "-m",
                self._fmt_controller_model,
                f"{charm_pull_path}/bundle.yaml",
            ]
        else:
            deploy_cmd_args = ["-m", self._fmt_controller_model, bundle]

        if bundle and overlay:
            tmp_file = tempfile.mkstemp()
            tmp_file_path = Path(tmp_file[-1])
            tmp_file_path.write_text(overlay, encoding="utf8")
            deploy_cmd_args.append("--overlay")
            deploy_cmd_args.append(str(tmp_file_path))
            os.close(tmp_file[0])
        if channel:
            deploy_cmd_args.append("--channel")
            deploy_cmd_args.append(channel)
        if constraints:
            deploy_cmd_args.append("--constraints")
            deploy_cmd_args.append(f"'{constraints}'")
        if series:
            deploy_cmd_args.append("--series")
            deploy_cmd_args.append(series)
        if force:
            deploy_cmd_args.append("--force")
        app.log.info(f"Deploying: juju deploy {' '.join(deploy_cmd_args)}")
        ret = cmd_ok(f"juju deploy {' '.join(deploy_cmd_args)}", shell=True,)
        if not ret.ok:
            raise SpecProcessException(f"Failed to deploy ({deploy_cmd_args}): {ret}")

    def _teardown(self):
        """ Destroy environment
        """
        try:
            for line in self.juju(
                "destroy-controller",
                "--destroy-all-models",
                "--destroy-storage",
                "-y",
                self.opt("controller"),
                _bg_exc=False,
                _iter=True,
            ):
                app.log.info(f" -- {line.strip()}")
        except sh.ErrorReturnCode as e:
            app.log.debug(
                f"Could not destroy controller: {e.stderr.decode().strip()}, no teardown performed."
            )

    def _bootstrap(self):
        """ Bootstraps environment
        """
        replace_controller = self.opt("bootstrap.replace-controller")
        if replace_controller:
            app.log.info(
                f"Replace controller triggered, will attempt to teardown {self.opt('controller')}"
            )
            self._teardown()

        bootstrap_cmd_args = ["bootstrap", self.opt("cloud"), self.opt("controller")]

        bootstrap_constraints = self.opt("bootstrap.constraints")
        if bootstrap_constraints:
            bootstrap_cmd_args.append("--bootstrap-constraints")
            bootstrap_cmd_args.append(bootstrap_constraints)

        bootstrap_series = self.opt("bootstrap.series")
        if bootstrap_series:
            bootstrap_cmd_args.append("--bootstrap-series")
            bootstrap_cmd_args.append(bootstrap_series)

        force = self.opt("force")
        if force:
            bootstrap_cmd_args.append("--force")

        model_defaults = self.opt("bootstrap.model-default")

        if model_defaults:
            for m_default in model_defaults:
                bootstrap_cmd_args.append("--model-default")
                bootstrap_cmd_args.append(m_default)

        config_defaults = self.opt("bootstrap.config")

        if config_defaults:
            for c_default in config_defaults:
                bootstrap_cmd_args.append("--config")
                bootstrap_cmd_args.append(c_default)

        bootstrap_debug = self.opt("bootstrap.debug")
        if bootstrap_debug:
            bootstrap_cmd_args.append("--debug")
        app.log.debug(f"Juju bootstrap cmd > {bootstrap_cmd_args}")
        try:
            for line in self.juju(
                *bootstrap_cmd_args, _iter=True, _bg_exc=False, _err_to_out=True
            ):
                app.log.info(line.strip())
        except sh.ErrorReturnCode as error:
            raise SpecProcessException(
                f"Unable to bootstrap:\n {error.stdout.decode()}"
            )

        disable_add_model = self.opt("bootstrap.disable-add-model")
        if not disable_add_model:
            app.log.info(f"Adding model {self._fmt_controller_model}")
            add_model_args = [
                "-c",
                self.opt("controller"),
                self.opt("model"),
                self.opt("cloud"),
            ]

            try:
                self.juju("add-model", *add_model_args)
            except sh.ErrorReturnCode as e:
                raise SpecProcessException(
                    f"Failed to add model: {e.stderr.decode().strip()}"
                )

    def _add_model(self):
        app.log.info(f"Adding model {self._fmt_controller_model}")
        add_model_args = [
            "-c",
            self.opt("controller"),
            self.opt("model"),
            self.opt("cloud"),
        ]

        try:
            self.juju("add-model", *add_model_args)
        except sh.ErrorReturnCode as e:
            raise SpecProcessException(
                f"Failed to add model: {e.stderr.decode().strip()}"
            )

    def _wait(self):
        deploy_wait = self.opt("deploy.wait") if self.opt("deploy.wait") else False
        deploy_timeout = (
            self.opt("deploy.timeout") if self.opt("deploy.timeout") else 7200
        )
        if deploy_wait:
            app.log.info("Waiting for deployment to settle")
            try:
                for line in self.juju_wait(
                    "-e",
                    self._fmt_controller_model,
                    "-w",
                    "-r3",
                    _iter=True,
                    _bg_exc=False,
                    _timeout=deploy_timeout,
                ):
                    app.log.debug(line.strip())
            except sh.ErrorReturnCode as e:
                raise SpecProcessException(
                    f"Failed to get a completed deployment status: {e.stderr.decode()}"
                )

    def process(self):
        """ Processes options
        """
        run = self.opt("bootstrap.run")
        if run:
            app.log.debug(
                "A runner override for bootstrapping found, executing instead."
            )
            return self._run(run)

        # Bootstrap unless reuse is true, controller and model must exist already
        reuse = self.opt("deploy.reuse")
        bootstrap = self.opt("bootstrap")
        if not reuse and bootstrap:
            self._bootstrap()

        # Do deploy
        if self.opt("deploy"):
            if self.opt("bootstrap.disable-add-model"):
                # Add model here since it wasn't done during bootstrap
                self._add_model()
            self._deploy()
            config_sets = self.opt("config")
            if config_sets:
                for config in config_sets:
                    app_name, setting = config.split(" ")
                    app.log.info(f"Setting {config}")
                    self.juju.config(
                        "-m", self._fmt_controller_model, app_name, setting
                    )
            self._wait()

        # Do teardown
        if self.opt("teardown"):
            self._teardown()

    def conflicts(self):
        bundle = self.opt("deploy.bundle")
        charm = self.opt("deploy.charm")

        if bundle and charm:
            raise SpecConfigException(
                "Can not have both bundle and charm defined in deployment, must choose one or the other."
            )


__class_plugin_obj__ = Juju
