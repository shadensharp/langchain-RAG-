import { useEffect, useState } from "react";
import { toast } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import { SourceBubble, Source } from "./SourceBubble";
import {
  VStack,
  Flex,
  Heading,
  HStack,
  Box,
  Button,
  Divider,
  Spacer,
  Link,
  Modal,
  ModalOverlay,
  ModalContent,
  ModalHeader,
  ModalCloseButton,
  ModalBody,
  ModalFooter,
  Text,
  Textarea,
} from "@chakra-ui/react";
import { InlineCitation } from "./InlineCitation";

export type MessageFeedback = {
  rating: "good" | "bad";
  comment?: string;
};

export type Message = {
  id: string;
  createdAt?: Date;
  content: string;
  rawContent?: string;
  role: "system" | "user" | "assistant" | "function";
  runId?: string;
  sources?: Source[];
  name?: string;
  status?: "pending" | "complete";
  feedback?: MessageFeedback;
  function_call?: { name: string };
};

const CITATION_PATTERN = /\[\^?\$?{?(\d+)}?\^?\]/g;
const EMPTY_SOURCES: Source[] = [];

const createAnswerElements = (
  content: string,
  sources: Source[],
  highlightedSourceLinkStates: boolean[],
  setHighlightedSourceLinkStates: React.Dispatch<
    React.SetStateAction<boolean[]>
  >,
) => {
  const matches = Array.from(content.matchAll(CITATION_PATTERN));
  const elements: JSX.Element[] = [];
  let prevIndex = 0;

  matches.forEach((match) => {
    const sourceNum = parseInt(match[1], 10);
    const sourceIndex = sourceNum - 1;
    const source = sources[sourceIndex];
    const matchIndex = match.index;
    if (matchIndex !== undefined && source !== undefined) {
      elements.push(
        <span
          key={`content:${prevIndex}`}
          dangerouslySetInnerHTML={{
            __html: content.slice(prevIndex, matchIndex),
          }}
        ></span>,
      );
      elements.push(
        <InlineCitation
          key={`citation:${prevIndex}`}
          source={source}
          sourceNumber={sourceNum}
          highlighted={highlightedSourceLinkStates[sourceIndex] ?? false}
          onMouseEnter={() =>
            setHighlightedSourceLinkStates(
              sources.map((_, index) => index === sourceIndex),
            )
          }
          onMouseLeave={() =>
            setHighlightedSourceLinkStates(sources.map(() => false))
          }
        />,
      );
      prevIndex = matchIndex + match[0].length;
    }
  });

  elements.push(
    <span
      key={`content:${prevIndex}`}
      dangerouslySetInnerHTML={{
        __html: content.slice(prevIndex),
      }}
    ></span>,
  );

  return elements;
};

const getTraceSources = (content: string, sources: Source[]) => {
  const citedSources: Source[] = [];
  const seen = new Set<number>();

  for (const match of Array.from(content.matchAll(CITATION_PATTERN))) {
    const citation = parseInt(match[1], 10);
    const source = sources[citation - 1];
    if (source !== undefined && !seen.has(citation)) {
      seen.add(citation);
      citedSources.push(source);
    }
  }

  return citedSources.length > 0 ? citedSources : sources;
};

export function ChatMessageBubble(props: {
  message: Message;
  onApproveResponse: (messageId: string) => Promise<void>;
  onRejectResponse: (messageId: string, comment: string) => Promise<void>;
}) {
  const { role, content, runId, status, feedback } = props.message;
  const isUser = role === "user";
  const sources = props.message.sources ?? EMPTY_SOURCES;

  const [isSubmittingFeedback, setIsSubmittingFeedback] = useState(false);
  const [badFeedbackIsOpen, setBadFeedbackIsOpen] = useState(false);
  const [traceIsOpen, setTraceIsOpen] = useState(false);
  const [feedbackComment, setFeedbackComment] = useState(feedback?.comment ?? "");
  const [highlightedSourceLinkStates, setHighlightedSourceLinkStates] = useState(
    sources.map(() => false),
  );

  useEffect(() => {
    setFeedbackComment(feedback?.comment ?? "");
  }, [feedback?.comment]);

  useEffect(() => {
    setHighlightedSourceLinkStates(sources.map(() => false));
  }, [sources]);

  const answerText = props.message.rawContent ?? content;
  const answerElements =
    role === "assistant"
      ? createAnswerElements(
          content,
          sources,
          highlightedSourceLinkStates,
          setHighlightedSourceLinkStates,
        )
      : [];
  const traceSources = getTraceSources(answerText, sources);
  const canLeaveFeedback = !isUser && status === "complete";

  const handleApprove = async () => {
    if (feedback !== undefined) {
      toast.error("This response already has feedback.");
      return;
    }

    setIsSubmittingFeedback(true);
    try {
      await props.onApproveResponse(props.message.id);
    } catch (error) {
      console.error("Failed to save positive feedback:", error);
      toast.error(
        error instanceof Error ? error.message : "Failed to save feedback.",
      );
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  const handleOpenBadFeedback = () => {
    if (feedback !== undefined) {
      toast.error("This response already has feedback.");
      return;
    }
    setBadFeedbackIsOpen(true);
  };

  const handleSubmitBadFeedback = async () => {
    const trimmedComment = feedbackComment.trim();
    if (!trimmedComment) {
      toast.error("Please describe what should change.");
      return;
    }

    setIsSubmittingFeedback(true);
    try {
      await props.onRejectResponse(props.message.id, trimmedComment);
      setBadFeedbackIsOpen(false);
    } catch (error) {
      console.error("Failed to save negative feedback:", error);
      toast.error(
        error instanceof Error ? error.message : "Failed to save feedback.",
      );
    } finally {
      setIsSubmittingFeedback(false);
    }
  };

  return (
    <VStack align="start" spacing={5} pb={5} width="100%">
      {!isUser && sources.length > 0 && (
        <>
          <Flex direction={"column"} width={"100%"}>
            <VStack spacing={"5px"} align={"start"} width={"100%"}>
              <Heading
                fontSize="lg"
                fontWeight={"medium"}
                mb={1}
                color={"blue.300"}
                paddingBottom={"10px"}
              >
                Sources
              </Heading>
              <HStack spacing={"10px"} maxWidth={"100%"} overflow={"auto"}>
                {sources.map((source, index) => (
                  <Box
                    key={`${source.citation}:${source.url}`}
                    alignSelf={"stretch"}
                    width={56}
                  >
                    <SourceBubble
                      source={source}
                      highlighted={highlightedSourceLinkStates[index] ?? false}
                      onMouseEnter={() =>
                        setHighlightedSourceLinkStates(
                          sources.map(
                            (_, sourceIndex) => sourceIndex === index,
                          ),
                        )
                      }
                      onMouseLeave={() =>
                        setHighlightedSourceLinkStates(sources.map(() => false))
                      }
                      runId={runId}
                    />
                  </Box>
                ))}
              </HStack>
            </VStack>
          </Flex>

          <Heading size="lg" fontWeight="medium" color="blue.300">
            Answer
          </Heading>
        </>
      )}

      {isUser ? (
        <Heading size="lg" fontWeight="medium" color="white">
          {content}
        </Heading>
      ) : (
        <Box className="whitespace-pre-wrap" color="white">
          {answerElements}
        </Box>
      )}

      {canLeaveFeedback && (
        <HStack spacing={2} width="100%" alignItems="center">
          <Button
            size="sm"
            variant={feedback?.rating === "good" ? "solid" : "outline"}
            colorScheme={feedback ? "gray" : "green"}
            onClick={handleApprove}
            isLoading={isSubmittingFeedback}
            isDisabled={feedback !== undefined}
          >
            Good
          </Button>
          <Button
            size="sm"
            variant={feedback?.rating === "bad" ? "solid" : "outline"}
            colorScheme={feedback ? "gray" : "orange"}
            onClick={handleOpenBadFeedback}
            isDisabled={feedback !== undefined}
          >
            Bad
          </Button>
          <Spacer />
          <Button
            size="sm"
            variant="outline"
            color="white"
            onClick={() => setTraceIsOpen(true)}
            isDisabled={traceSources.length === 0}
          >
            Trace
          </Button>
        </HStack>
      )}

      {!isUser && feedback?.rating === "good" && (
        <Text fontSize="sm" color="green.300">
          Saved. Later answers will try to continue this response style.
        </Text>
      )}

      {!isUser && feedback?.rating === "bad" && (
        <Text fontSize="sm" color="orange.300">
          Saved. Later answers will adapt to your feedback.
        </Text>
      )}

      {!isUser && <Divider mt={4} mb={4} />}

      <Modal isOpen={badFeedbackIsOpen} onClose={() => setBadFeedbackIsOpen(false)}>
        <ModalOverlay />
        <ModalContent backgroundColor={"rgb(38, 38, 41)"} color="white">
          <ModalHeader>Add Feedback</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text fontSize="sm" color="gray.300" mb={3}>
              Describe what should change in future answers. This can include
              language, tone, structure, or wording habits.
            </Text>
            <Textarea
              value={feedbackComment}
              onChange={(event) => setFeedbackComment(event.target.value)}
              minH="140px"
              placeholder="Example: Use Chinese, start with the conclusion, and keep the wording plain."
              bg={"rgba(255, 255, 255, 0.06)"}
              borderColor={"rgb(80, 80, 84)"}
              _focus={{
                borderColor: "blue.400",
                boxShadow: "0 0 0 1px #4299E1",
              }}
            />
          </ModalBody>
          <ModalFooter>
            <Button variant="ghost" mr={3} onClick={() => setBadFeedbackIsOpen(false)}>
              Cancel
            </Button>
            <Button
              colorScheme="orange"
              onClick={handleSubmitBadFeedback}
              isLoading={isSubmittingFeedback}
            >
              Save Feedback
            </Button>
          </ModalFooter>
        </ModalContent>
      </Modal>

      <Modal isOpen={traceIsOpen} onClose={() => setTraceIsOpen(false)} size="3xl">
        <ModalOverlay />
        <ModalContent backgroundColor={"rgb(38, 38, 41)"} color="white">
          <ModalHeader>Answer Trace</ModalHeader>
          <ModalCloseButton />
          <ModalBody>
            <Text fontSize="sm" color="gray.300" mb={4}>
              These are the cited or retrieved source chunks behind this answer,
              including their document location, original link, and retrieved
              excerpt.
            </Text>
            <VStack spacing={4} align="stretch">
              {traceSources.map((source) => (
                <Box
                  key={`${source.citation}:${source.url}`}
                  borderWidth="1px"
                  borderColor="rgba(255,255,255,0.12)"
                  borderRadius="md"
                  p={4}
                  bg="rgba(255, 255, 255, 0.04)"
                >
                  <Text fontSize="sm" color="blue.200" mb={2}>
                    [{source.citation}] {source.title}
                  </Text>
                  <Text fontSize="xs" color="gray.400" mb={2}>
                    Document location
                  </Text>
                  <Text fontSize="sm" color="gray.100" mb={3}>
                    {source.location}
                  </Text>
                  <Text fontSize="xs" color="gray.400" mb={2}>
                    Source link
                  </Text>
                  {source.url ? (
                    <Link href={source.url} color="blue.200" isExternal>
                      {source.url}
                    </Link>
                  ) : (
                    <Text fontSize="sm" color="gray.400">
                      This source does not include a link.
                    </Text>
                  )}
                  <Text fontSize="xs" color="gray.400" mt={4} mb={2}>
                    Retrieved excerpt
                  </Text>
                  <Box
                    bg="rgba(0, 0, 0, 0.22)"
                    borderRadius="md"
                    padding={3}
                    fontSize="sm"
                    whiteSpace="pre-wrap"
                    color="gray.100"
                  >
                    {source.excerpt}
                  </Box>
                </Box>
              ))}
            </VStack>
          </ModalBody>
          <ModalFooter>
            <Button onClick={() => setTraceIsOpen(false)}>Close</Button>
          </ModalFooter>
        </ModalContent>
      </Modal>
    </VStack>
  );
}
