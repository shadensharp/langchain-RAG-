import "react-toastify/dist/ReactToastify.css";
import { Card, CardBody, Heading, Text } from "@chakra-ui/react";
import { sendFeedback } from "../utils/sendFeedback";

export type Source = {
  citation: number;
  url: string;
  title: string;
  location: string;
  excerpt: string;
};

export function SourceBubble({
  source,
  highlighted,
  onMouseEnter,
  onMouseLeave,
  runId,
}: {
  source: Source;
  highlighted: boolean;
  onMouseEnter: () => any;
  onMouseLeave: () => any;
  runId?: string;
}) {
  return (
    <Card
      onClick={async () => {
        window.open(source.url, "_blank");
        if (runId) {
          await sendFeedback({
            key: "user_click",
            runId,
            value: source.url,
            isExplicit: false,
          });
        }
      }}
      backgroundColor={highlighted ? "rgb(58, 58, 61)" : "rgb(78,78,81)"}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      cursor={"pointer"}
      alignSelf={"stretch"}
      height="100%"
      overflow={"hidden"}
    >
      <CardBody>
        <Text fontSize={"xs"} color={"blue.200"} mb={2}>
          [{source.citation}] Source
        </Text>
        <Heading size={"sm"} fontWeight={"normal"} color={"white"}>
          {source.title}
        </Heading>
        <Text fontSize={"xs"} color={"gray.400"} mt={2} noOfLines={1}>
          {source.location}
        </Text>
      </CardBody>
    </Card>
  );
}
