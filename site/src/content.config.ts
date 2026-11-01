import { defineCollection } from "astro:content";
import { docsLoader } from "@astrojs/starlight/loaders";
import { docsSchema } from "@astrojs/starlight/schema";
import { z } from "astro/zod";
import { repositoryVersionFacts, resolveFactTokens } from "../scripts/version-facts";

/** Journey text may cite a current version only through a `%%fact=<name>%%` token. */
const factText = () => z.string().transform((value) => resolveFactTokens(value, repositoryVersionFacts(), "journey frontmatter"));

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        journey: z.object({
          level: z.enum(["Foundation", "Practitioner", "Power user", "Reference", "Labs", "Academy"]),
          time: factText(),
          outcome: factText(),
          prerequisites: z.array(factText()).optional(),
          proof: factText().optional(),
        }).optional(),
        academySource: z.object({
          release: z.string(),
          commit: z.string(),
        }).optional(),
      }),
    }),
  }),
};
