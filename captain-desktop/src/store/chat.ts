import { create } from "zustand";
import { api, Conversation, Message, streamChat } from "../lib/api";

interface ChatState {
  conversations: Conversation[];
  activeConversationId: string | null;
  messages: Message[];
  streaming: boolean;
  streamingText: string;

  loadConversations: () => Promise<void>;
  selectConversation: (id: string) => Promise<void>;
  newConversation: () => Promise<void>;
  sendMessage: (text: string) => Promise<void>;
  deleteConversation: (id: string) => Promise<void>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  streaming: false,
  streamingText: "",

  loadConversations: async () => {
    const convs = await api.conversations.list();
    set({ conversations: convs });
  },

  selectConversation: async (id) => {
    const conv = await api.conversations.get(id);
    set({
      activeConversationId: id,
      messages: conv.messages ?? [],
    });
  },

  newConversation: async () => {
    const { id } = await api.conversations.create();
    await get().loadConversations();
    set({ activeConversationId: id, messages: [] });
  },

  sendMessage: async (text) => {
    const { activeConversationId, messages } = get();

    // Optimistically add user message
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    set({ messages: [...messages, userMsg], streaming: true, streamingText: "" });

    let conversationId = activeConversationId ?? undefined;
    let assistantText = "";

    try {
      for await (const event of streamChat(text, conversationId)) {
        if (event.type === "conversation_id") {
          conversationId = (event.data as { id: string }).id;
          if (!get().activeConversationId) {
            set({ activeConversationId: conversationId });
          }
        } else if (event.type === "token") {
          const chunk = (event.data as { text: string; done: boolean });
          assistantText += chunk.text;
          set({ streamingText: assistantText });
        }
      }
    } finally {
      const assistantMsg: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        content: assistantText,
        created_at: new Date().toISOString(),
      };
      set((s) => ({
        messages: [...s.messages, assistantMsg],
        streaming: false,
        streamingText: "",
      }));
      await get().loadConversations();
    }
  },

  deleteConversation: async (id) => {
    await api.conversations.delete(id);
    const { activeConversationId } = get();
    if (activeConversationId === id) {
      set({ activeConversationId: null, messages: [] });
    }
    await get().loadConversations();
  },
}));
