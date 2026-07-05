"use client";

import { MessageCircle } from "@/components/brand/icons";
import { Button, Card, CardBody } from "@/components/ui";

export function SparseProfileCard({ onAskAarya }: { onAskAarya?: () => void }) {
  return (
    <Card>
      <CardBody className="space-y-3">
        <p className="text-h3 text-ink-900">A few details unlock better matches</p>
        <p className="text-small text-ink-500">
          Tell Aarya about your last role, target CTC, and notice period — three minutes in chat
          or voice.
        </p>
        <Button
          size="sm"
          variant="secondary"
          leftIcon={<MessageCircle className="h-4 w-4" />}
          onClick={onAskAarya}
        >
          Continue in chat
        </Button>
      </CardBody>
    </Card>
  );
}
