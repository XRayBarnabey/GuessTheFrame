import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react'
import { useQuery } from '@tanstack/react-query'
import { LoaderCircle, Search, Sparkles } from 'lucide-react'
import clsx from 'clsx'
import { api } from '../lib/api'
import type { TitleSuggestions } from '../lib/types'

export function TitleAutocomplete({
  value,
  onChange,
  placeholder = 'Titre du film ou nom de la série…',
  inputId = 'guess',
  disabled = false,
}: {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  inputId?: string
  disabled?: boolean
}) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const [debounced, setDebounced] = useState(value)
  const wrapperRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value.trim()), 220)
    return () => window.clearTimeout(timer)
  }, [value])

  const query = useQuery({
    queryKey: ['title-suggestions', debounced],
    queryFn: () =>
      api.get<TitleSuggestions>(
        `/api/catalogue/titles?q=${encodeURIComponent(debounced)}`,
      ),
    enabled: debounced.length >= 2,
    staleTime: 60_000,
  })

  const items = useMemo(() => query.data?.items ?? [], [query.data])

  useEffect(() => {
    setHighlighted(0)
  }, [debounced])

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  function selectSuggestion(title: string) {
    onChange(title)
    setOpen(false)
    setDebounced(title)
  }

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setHighlighted((current) => Math.min(current + 1, Math.max(0, items.length - 1)))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((current) => Math.max(0, current - 1))
    } else if (event.key === 'Enter' && open && items.length > 0) {
      event.preventDefault()
      selectSuggestion(items[highlighted]?.title ?? items[0].title)
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  const showDropdown = open && debounced.length >= 2

  return (
    <div ref={wrapperRef} className="relative flex-1">
      <Search
        size={17}
        className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-sand-500"
      />
      <input
        id={inputId}
        value={value}
        onChange={(event) => {
          onChange(event.target.value)
          setOpen(true)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        autoComplete="off"
        autoFocus
        maxLength={500}
        disabled={disabled}
        role="combobox"
        aria-expanded={showDropdown}
        aria-controls={`${inputId}-suggestions`}
        aria-autocomplete="list"
        className="h-12 w-full border border-cream-100/12 bg-ink-950/60 pl-10 pr-3 text-sm text-cream-100 outline-none transition-colors placeholder:text-sand-500/60 focus:border-gold-400/60"
      />
      {showDropdown && (
        <div
          id={`${inputId}-suggestions`}
          role="listbox"
          className="absolute left-0 right-0 top-[calc(100%+0.35rem)] z-30 max-h-72 overflow-y-auto border border-cream-100/15 bg-ink-900 shadow-2xl shadow-black/30"
        >
          {query.isFetching && (
            <div className="flex items-center gap-2 px-3 py-3 text-[0.68rem] text-sand-500">
              <LoaderCircle size={14} className="animate-spin text-gold-400" />
              Recherche dans le catalogue…
            </div>
          )}
          {!query.isFetching && items.length === 0 && (
            <div className="px-3 py-3 text-[0.68rem] text-sand-500">
              Aucun titre correspondant.
            </div>
          )}
          {items.map((item, index) => (
            <button
              key={`${item.type}-${item.title}-${index}`}
              type="button"
              role="option"
              aria-selected={index === highlighted}
              onMouseEnter={() => setHighlighted(index)}
              onClick={() => selectSuggestion(item.title)}
              className={clsx(
                'flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left transition-colors',
                index === highlighted
                  ? 'bg-gold-400/10 text-cream-100'
                  : 'text-sand-400 hover:bg-cream-100/[0.04]',
              )}
            >
              <span className="flex min-w-0 items-center gap-2">
                <Sparkles size={12} className="shrink-0 text-gold-400" />
                <span className="truncate text-sm">{item.title}</span>
              </span>
              <span className="shrink-0 text-[0.58rem] uppercase tracking-[0.12em] text-sand-500">
                {item.type === 'episode' ? 'Série' : 'Film'}
                {item.year ? ` · ${item.year}` : ''}
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
