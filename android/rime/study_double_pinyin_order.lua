-- SPDX-License-Identifier: GPL-3.0-or-later
return {
  tags_match = function(segment, env)
    return segment.length == 3 and segment:has_tag("abc")
      and env.engine.context.input:sub(segment.start + 1, segment._end):match("^[a-z]+$") ~= nil
  end,

  func = function(input)
    local has_full_pair = false
    local partial, fallback = {}, {}
    for cand in input:iter() do
      local start = cand.start
      local length = cand._end - start
      local spans = cand:spans()
      -- Use Rime's actual syllable boundaries, including for learned phrases.
      if length == 3 and spans.count == 2 and spans:has_vertex(start + 2) then
        has_full_pair = true
        yield(cand)
      elseif length == 2 and spans.count == 1 then
        partial[#partial + 1] = cand
      else
        fallback[#fallback + 1] = { candidate = cand, initials = spans.count == 3 }
      end
    end

    for _, cand in ipairs(partial) do yield(cand) end
    if not has_full_pair and #partial == 0 then
      -- Keep Rime's original order for three initials with no leading double-pinyin syllable.
      for _, entry in ipairs(fallback) do yield(entry.candidate) end
      return
    end
    for _, entry in ipairs(fallback) do
      if not entry.initials then yield(entry.candidate) end
    end
    for _, entry in ipairs(fallback) do
      if entry.initials then yield(entry.candidate) end
    end
  end,
}
