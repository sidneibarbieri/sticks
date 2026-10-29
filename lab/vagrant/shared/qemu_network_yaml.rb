require "json"
require "yaml"

# JSON is valid YAML and preserves MAC strings across Ruby and cloud-init parsers.
module SticksQemuNetworkYaml
  module StringSafeSerialization
    def build_network_config(**options)
      JSON.generate(YAML.safe_load(super))
    end
  end

  def self.install!
    network = VagrantPlugins::QEMU::Network.singleton_class
    network.prepend(StringSafeSerialization) unless network.ancestors.include?(StringSafeSerialization)
  end
end
