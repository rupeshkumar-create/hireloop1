-- Rename MSG91-specific column after migrating to Gupshup WhatsApp.
ALTER TABLE public.whatsapp_messages
  RENAME COLUMN msg91_id TO external_message_id;

COMMENT ON COLUMN public.whatsapp_messages.external_message_id IS
  'Provider message ID (Gupshup messageId) for delivery audit.';
