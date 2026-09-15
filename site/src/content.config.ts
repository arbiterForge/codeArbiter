import { defineCollection } from "astro:content";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";
import { z } from "astro/zod";

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        journey: z.object({
          level: z.enum(["Foundation", "Practitioner", "Power user", "Reference", "Labs", "Academy"]),
          time: z.string(),
          outcome: z.string(),
          prerequisites: z.array(z.string()).optional(),
          proof: z.string().optional(),
        }).optional(),
        academySource: z.object({
          release: z.string(),
          commit: z.string(),
        }).optional(),
      }),
    }),
  }),
};
