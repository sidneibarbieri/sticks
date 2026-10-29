# Deterministic SSH forwarding for concurrent isolated QEMU laboratories.
module SticksQemuSshPort
  OFFSET_ENVIRONMENT = "STICKS_QEMU_PORT_OFFSET"
  MAX_OFFSET = 1_000

  def self.for(default_port)
    offset = Integer(ENV.fetch(OFFSET_ENVIRONMENT, "0"), 10)
    unless (0..MAX_OFFSET).cover?(offset)
      raise "#{OFFSET_ENVIRONMENT} must be between 0 and #{MAX_OFFSET}"
    end

    default_port + offset
  end
end
