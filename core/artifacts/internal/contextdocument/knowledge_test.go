package contextdocument

import (
	"strings"
	"testing"
)

func TestConfigOnlyControlsPreservesNestedScopeBlocks(t *testing.T) {
	source := []byte("# Security controls\n\n<!-- migration-paths -->\n+ db/**\n<!-- ci-paths -->\n+ .github/**\n<!-- /ci-paths -->\n<!-- /migration-paths -->\n")
	output, err := ConfigOnlyControls(source)
	if err != nil {
		t.Fatal(err)
	}
	converted := string(output)
	for _, want := range []string{"<!-- migration-paths -->", "<!-- /migration-paths -->", "<!-- ci-paths -->", "<!-- /ci-paths -->"} {
		if !strings.Contains(converted, want) {
			t.Fatalf("conversion dropped an operative scope delimiter %q: %s", want, converted)
		}
	}
}

func TestHeadingOnlyMarkdownHasContent(t *testing.T) {
	if !HasContent([]byte("# Never commit secrets\n"), 0) {
		t.Fatal("a heading that states a rule was treated as empty content")
	}
}

func TestHasContentKeepsTextAfterComments(t *testing.T) {
	for _, source := range []string{
		"<!-- explanation --> Never log tokens\n",
		"<!-- explanation\ncontinued --> Never log tokens\n",
		"<!-- unfinished comment\nNever log tokens\n",
	} {
		if !HasContent([]byte(source), 0) {
			t.Fatalf("visible or uncertain Markdown was treated as empty: %q", source)
		}
	}
}

func TestConfigOnlyControlsRejectsMismatchedScopeBlocks(t *testing.T) {
	_, err := ConfigOnlyControls([]byte("<!-- migration-paths -->\n+ db/**\n<!-- /ci-paths -->\n"))
	if err == nil {
		t.Fatal("mismatched scope tags could remove operative configuration")
	}
}

func TestSectionsHandlesEmptyOptionalSource(t *testing.T) {
	sections, err := Sections(nil, 0, "Tech stack")
	if err != nil || len(sections) != 0 {
		t.Fatalf("empty optional document: sections=%v err=%v", sections, err)
	}
}

func TestSectionsDistinguishesGenericTitleFromRuleHeading(t *testing.T) {
	sections, err := Sections([]byte("# Security controls\n\n## Never commit secrets\n"), 0, "Security controls")
	if err != nil || len(sections) != 2 || sections[0].Content || !sections[1].Content {
		t.Fatalf("section content classification: sections=%v err=%v", sections, err)
	}
}
