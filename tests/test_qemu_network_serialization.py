"""The guest parser must receive MAC addresses as strings, never YAML numbers."""

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


COMPATIBILITY = Path(__file__).resolve().parents[1] / "lab/vagrant/shared/qemu_network_yaml.rb"


@pytest.mark.parametrize("mac", ["52:54:00:35:54:10", "52:54:00:00:00:01", "52:54:00:ab:cd:ef"])
def test_cloud_init_mac_string_survives_guest_yaml_parser(mac):
    ruby = shutil.which("ruby")
    if not ruby:
        pytest.skip("Ruby is required to exercise the Vagrant serialization boundary")
    program = r'''
require "yaml"
module VagrantPlugins
  module QEMU
    module Network
      def self.build_network_config(mac0:, mac1:, ip:, netmask:)
        {"network" => {"version" => 2, "ethernets" => {
          "user-nic" => {"match" => {"macaddress" => mac0}, "dhcp4" => true},
          "private-nic" => {"match" => {"macaddress" => mac1}, "addresses" => ["#{ip}/24"]}
        }}}.to_yaml
      end
    end
  end
end
if File.exist?(ARGV[0])
  require ARGV[0]
  SticksQemuNetworkYaml.install!
  SticksQemuNetworkYaml.install!
end
puts VagrantPlugins::QEMU::Network.build_network_config(
  mac0: ARGV[1], mac1: ARGV[1], ip: "192.168.56.10", netmask: "255.255.255.0")
'''
    result = subprocess.run([ruby, "-e", program, str(COMPATIBILITY), mac], capture_output=True, text=True, check=True)
    ethernets = yaml.safe_load(result.stdout)["network"]["ethernets"]
    assert ethernets["user-nic"]["match"]["macaddress"] == mac
    assert ethernets["private-nic"]["match"]["macaddress"] == mac
    assert ethernets["user-nic"]["dhcp4"] is True
    assert ethernets["private-nic"]["addresses"] == ["192.168.56.10/24"]
