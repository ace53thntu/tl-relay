# Emits one line per finding:
#   EMPTY\t                                the fragment requires nothing
#   MISSING\t<event> <matcher> <command>   registered nowhere in the live file
#   SCRIPT\t<path>                         a script path to test for existence
#   NOSCRIPT\t<event> <matcher> <command>  a fragment entry with no quoted path
#
# $f is the fragment, $l the live settings, both --slurpfile so an unreadable
# file is a jq error rather than an empty comparison that would pass.
#
# The script path is the single-quoted string that ends the command.
def triples:
  (.[0].hooks // {}) | to_entries
  | map(
      .key as $event
      | .value[]
      | (.matcher // "*") as $matcher
      | (.hooks // [])[]
      | (.command // "") as $command
      | { id: ($event + " " + $matcher + " " + $command),
          script: ([$command | capture("'(?<p>[^']+)'$") | .p][0]) }
    );

($f | triples) as $want
| ($l | triples | map(.id)) as $have
| ( (if ($want | length) == 0 then ["EMPTY\t"] else [] end)
  + [ $want[] | .id as $k | select(($have | index($k)) == null) | "MISSING\t" + $k ]
  + [ $want[] | select(.script != null)                        | "SCRIPT\t"  + .script ]
  + [ $want[] | select(.script == null)                        | "NOSCRIPT\t" + .id ] )
| .[]
