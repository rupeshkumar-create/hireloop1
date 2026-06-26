-- Restore MSG91 provider comment on whatsapp_messages.external_message_id.
COMMENT ON COLUMN public.whatsapp_messages.external_message_id IS
  'Provider message ID (MSG91) for delivery audit.';
