"""
This module contains logic to assist with various
authorisation tasks against the open science grid.

This will ultimately be a good candidate to spin-out
into its own package.
"""

import subprocess
import configparser
import logging

from asimov import config


def refresh_scitoken(func):
    """
    Decorator to refresh an existing scitoken.
    """

    def wrapper(*args, **kwargs):
        logger = logging.getLogger("asimov").getChild("auth")

        try:
            command = ["kinit"] + [config.get("authentication", "kinit options")]

            pipe = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            logger.info(" ".join(command))
            out, err = pipe.communicate()
            logger.info(out)
            if err and len(err) > 0:
                logger.error(err)

            command = ["htgettoken"] + [
                config.get("authentication", "htgettoken options")
            ]

            pipe = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            logger.info(" ".join(command))
            out, err = pipe.communicate()
            logger.info(out)
            if err and len(err) > 0:
                logger.error(err)

            command = ["condor_vault_storer"] + [config.get("authentication", "scopes")]

            pipe = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
            )
            logger.info(" ".join(command))
            out, err = pipe.communicate()
            logger.info(out)
            if err and len(err) > 0:
                logger.error(err)

        except configparser.NoSectionError:
            # If authentication isn't set up then just ignore this.
            pass

        func(*args, **kwargs)

    return wrapper
