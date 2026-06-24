/**
 * Barrel export for the design-system primitives.
 *
 *   import { Button, Card, Input, Field, EmptyState } from "@/components/ui";
 *
 * Every primitive in here follows DESIGN.md. If you need something that
 * isn't here, propose it in the doc first — don't ship one-off styles.
 */

export { Button } from "./Button";
export { Card, CardHeader, CardBody, CardFooter } from "./Card";
export { Input, Textarea, Select, Field } from "./Input";
export { Avatar } from "./Avatar";
export { Badge } from "./Badge";
export { ScoreDot } from "./ScoreDot";
export { EmptyState } from "./EmptyState";
export { Modal, ModalFooter } from "./Modal";
export { ToastProvider, useToast } from "./Toast";
