# -*- coding: utf-8 -*-

import click
import createrepo_c as cr
import gi
import logging
import os
import stat
import sys


gi.require_version('Modulemd', '2.0')  # noqa
from gi.repository import Modulemd

from dnf.subject import Subject
import hawkey

DEFAULT_PROFILE = 'everything'


def parse_repodata(path):
    """
    Return a list of packages included in this repository
    """
    try:
        repomd = cr.Repomd(os.path.join(path, "repodata/repomd.xml"))
    except OSError as e:
        error(e)
        exit(2)

    for record in repomd.records:
        if record.type == "primary":
            primary_xml_path = record.location_href

    def warningcb(warning_type, message):
        """Optional callback for warnings about
        wierd stuff and formatting in XML.
        :param warning_type: Integer value. One from
                             the XML_WARNING_* constants.
        :param message: String message.
        """
        logging.warning("PARSER WARNING: %s" % message)
        return True

    packages = []

    def pkgcb(pkg):
        # Called when whole package entry in xml is parsed
        packages.append(pkg)

    cr.xml_parse_primary(os.path.join(path, primary_xml_path),
                         pkgcb=pkgcb,
                         do_files=False,
                         warningcb=warningcb)

    return packages


def get_source_packages(packages):
    """
    Return the unique set of source package names
    """
    source_packages = set()
    for pkg in packages:
        # Get the source RPM NEVRA without the trailing ".rpm"
        subject = Subject(pkg.rpm_sourcerpm[:-4])

        # Now get just the source RPM name
        nevras = subject.get_nevra_possibilities(forms=[hawkey.FORM_NEVRA])
        for nevra in nevras:
            source_packages.add(nevra.name)

    return source_packages


@click.command()
@click.option('-d', '--debug/--nodebug', default=False)
@click.option('-n', '--module-name',
              default=lambda: os.path.basename(os.environ.get('PWD')),
              show_default='Current directory name')
@click.option('-s', '--module-stream',
              default='rolling',
              show_default=True)
@click.option('-v', '--module-version',
              default=1,
              show_default=True)
@click.option('-c', '--module-context',
              default='abcdef12',
              show_default=True)
@click.argument('repo_path', type=click.Path(exists=True))
@click.argument('modules_yaml', default='modules.yaml')
def cli(debug,
        module_name,
        module_stream,
        module_version,
        module_context,
        repo_path,
        modules_yaml):

    if debug:
        logging.basicConfig(level=logging.DEBUG)

    abs_repo_path = os.path.abspath(repo_path)
    abs_modules_yaml = os.path.abspath(modules_yaml)

    packages = parse_repodata(abs_repo_path)

    # Create module stream framework
    stream = Modulemd.ModuleStreamV2.new(module_name, module_stream)
    stream.set_version(module_version)
    stream.set_context(module_context)
    stream.set_summary('<auto-generated module summary>')
    stream.set_description('<auto-generated module description>')
    stream.add_module_license("MIT")
    stream.add_content_license("<FILL THIS IN>")

    source_packages = get_source_packages(packages)

    for srcpkg in source_packages:
        component = Modulemd.ComponentRpm.new(srcpkg)
        component.set_rationale('Present in the repository')
        stream.add_component(component)

    common_profile = Modulemd.Profile.new(DEFAULT_PROFILE)

    for pkg in packages:
        stream.add_rpm_artifact(pkg.nevra())
        stream.add_rpm_api(pkg.name)
        common_profile.add_rpm(pkg.name)

    stream.add_profile(common_profile)

    # Add defaults for this module
    defaults = Modulemd.DefaultsV1.new(module_name)
    defaults.set_default_stream(module_stream)
    defaults.add_default_profile_for_stream(module_stream, DEFAULT_PROFILE)

    index = Modulemd.ModuleIndex.new()
    index.add_module_stream(stream)
    index.add_defaults(defaults)

    logging.debug("Writing YAML to {}".format(abs_modules_yaml))
    try:
        with open(abs_modules_yaml, 'w') as output:
            output.write(index.dump_to_string())
    except PermissionError as e:
        logging.error("Could not write YAML to file: {}".format(e))
        exit(3)


if __name__ == "__main__":
    cli()
