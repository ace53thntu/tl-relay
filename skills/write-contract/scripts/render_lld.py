#!/usr/bin/env python3
"""Render an OpenAPI contract into the route pages and the common errors beside its LLD."""
import argparse
import json
import sys

from contract import ContractError, bundle, common_link, load_module, render_module, retitle, save_module


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--contract", required=True)
    p.add_argument("--lld", required=True)
    p.add_argument("--module")
    p.add_argument("--common")
    p.add_argument("--check", action="store_true")
    p.add_argument("--retitle", action="store_true",
                   help="retitle existing route pages from their summaries and update link texts on the common page")
    args = p.parse_args(argv)
    try:
        doc, raw = bundle(args.contract), bundle(args.contract, dereferenced=False)
        module, pages, contracts = load_module(args.lld, args.module, args.common)
        new_pages, new_contracts = render_module(doc, raw, module, pages, contracts,
                                              common_link(args.lld, module, args.common))
        renames = {}
        if args.retitle:
            new_pages, renames = retitle(doc, new_pages, module)
            for old, new in renames.items():
                new_contracts = new_contracts.replace(f"[{old}]", f"[{new}]")
    except ContractError as e:
        print(f"render_lld: {e}", file=sys.stderr)
        return 1
    changed = sorted(k for k, v in new_pages.items() if v != pages.get(k))
    if new_contracts != contracts:
        changed.append(args.common or f"{module}/interface-contracts.md")
    if args.check:
        print("up to date" if not changed else "stale: " + ", ".join(changed))
        return 1 if changed else 0
    if changed:
        save_module(args.lld, new_pages, new_contracts, args.module, args.common)
    out = {"routes": len(new_pages), "changed": changed}
    if args.retitle:
        out["retitled"] = renames
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
