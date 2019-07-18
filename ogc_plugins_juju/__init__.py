""" OGC Juju Plugin - juju access
"""

import os
import click
import sys
import sh
import uuid
import yaml
from tempfile import gettempdir
from melddict import MeldDict
from ogc import log
from ogc.state import app
from ogc.spec import SpecPlugin, SpecProcessException


class Juju(SpecPlugin):
    """ OGC Juju Plugin
    """

    friendly_name = "Juju Plugin"

    options = [
        ("cloud", True),
        ("controller", True),
        ("model", True),
        ("bootstrap", True),
        ("bootstrap.constraints", False),
        ("bootstrap.debug", False),
        ("bootstrap.disable_add_model", False),
        ("deploy", False),
        ("deploy.reuse", False),
        ("deploy.bundle", True),
        ("deploy.overlay", False),
        ("deploy.bundle_channel", True),
        ("deploy.charm_channel", True),
        ("deploy.wait", False),
        ("config", False),
        ("config.set", False),
    ]

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

    @property
    def _fmt_controller_model(self):
        return f"{self.get_option('controller')}:{self.get_option('model')}"

    def _deploy(self):
        """ Handles juju deploy
        """
        bundle = self.get_option("deploy.bundle")
        overlay = self.get_option("deploy.overlay")
        bundle_channel = self.get_option("deploy.bundle_channel")
        charm_channel = self.get_option("deploy.charm_channel")

        deploy_cmd_args = []
        charm_pull_args = []
        if bundle.startswith("cs:"):
            charm_pull_args.append(bundle)
            tmpsuffix = str(uuid.uuid4()).split("-").pop()
            charm_pull_path = f"{gettempdir()}/{tmpsuffix}"

            if bundle_channel:
                charm_pull_args.append("--channel")
                charm_pull_args.append(bundle_channel)
                charm_pull_args.append(charm_pull_path)

            # Access charmstore bundle
            self.charm.pull(*charm_pull_args)
            deploy_cmd_args = [
                "-m",
                self._fmt_controller_model,
                f"{charm_pull_path}/bundle.yaml",
            ]
            if overlay:
                deploy_cmd_args.append("--overlay")
                deploy_cmd_args.append(overlay)
            if charm_channel:
                deploy_cmd_args.append("--channel")
                deploy_cmd_args.append(charm_channel)
            for line in self.juju.deploy(
                *deploy_cmd_args, _iter=True, _err_to_out=True
            ):
                line = line.strip()
                log.info(line)
        else:
            deploy_cmd_args = ["-m", self._fmt_controller_model, bundle]
            for line in self.juju.deploy(
                *deploy_cmd_args, _iter=True, _err_to_out=True
            ):
                line = line.strip()
                log.info(line)

    def _bootstrap(self):
        """ Bootstraps environment
        """
        bootstrap_cmd_args = [
            "bootstrap",
            self.get_option("cloud"),
            self.get_option("controller"),
        ]
        bootstrap_constraints = self.get_option("bootstrap.constraints")
        if bootstrap_constraints:
            bootstrap_cmd_args.append("--bootstrap-constraints")
            bootstrap_cmd_args.append(bootstrap_constraints)

        bootstrap_debug = self.get_option("bootstrap.debug")
        if bootstrap_debug:
            bootstrap_cmd_args.append("--debug")
        try:
            for line in self.juju(*bootstrap_cmd_args, _iter=True, _err_to_out=True):
                log.debug(line.strip())
        except sh.ErrorReturnCode_1 as e:
            raise SpecProcessException(f"Unable to bootstrap:\n {e.stdout.decode()}")

        disable_add_model = self.get_option("bootstrap.disable_add_model")
        if not disable_add_model:
            log.info(f"Adding model {self._fmt_controller_model}")
            add_model_args = [
                "-c",
                self.get_option("controller"),
                self.get_option("model"),
                self.get_option("cloud"),
            ]

            self.juju("add-model", *add_model_args)

    def _wait(self):
        deploy_wait = (
            self.get_option("deploy.wait") if self.get_option("deploy.wait") else False
        )
        if deploy_wait:
            log.info("Waiting for deployment to settle")
            for line in self.juju_wait(
                "-e",
                self._fmt_controller_model,
                "-w",
                "-r3",
                "-t14400",
                _iter=True,
                _err_to_out=True,
            ):
                log.debug(line.strip())

    def process(self):
        """ Processes options
        """
        # Bootstrap unless reuse is true, controller and model must exist already
        if not self.get_option("deploy.reuse") and self.get_option("bootstrap"):
            self._bootstrap()

        # Do deploy
        if self.get_option("deploy"):
            self._deploy()
            self._wait()
            config_sets = self.get_option("config.set")
            if config_sets:
                for config in config_sets:
                    app_name, setting = config.split(" ")
                    log.info(f"Setting {config}")
                    self.juju.config(
                        "-m", self._fmt_controller_model, app_name, setting
                    )
            self._wait()

    def doc(self):
        """
        [Juju]
        # Juju module for bootstrapping and deploying a bundle
        cloud = "aws"

        # controller to create
        controller = "validator"

        # model to create
        model = "validator-model"

        [Juju.bootstrap]
        # turn on debugging
        debug = false

        # disable adding the specified model, usually when some configuration on the
        # models have to be done
        disable-add-model = true

        [Juju.deploy]
        # reuse existing controller/model
        reuse = True

        # bundle to deploy
        # bundle = "cs:~owner/custom-bundle"
        bundle = "bundles/my-custom-bundle.yaml"

        # Optional overlay to pass into juju
        overlay = "overlays/1.15-edge.yaml"

        # Optional bundle channel to deploy from
        bundle_channel = "edge"

        # Optional charm channel to deploy from
        charm_channel = "edge"

        # Wait for a deployment to settle?
        wait = true

        [Juju.config]
        # Config options to pass to a deployed application
        # ie, juju config -m controller:model kubernetes-master allow-privileged=true
        set = ["kubernetes-master = allow-privileged=true",
               "kubernetes-worker = allow-privileged=true"]
        """
        return
