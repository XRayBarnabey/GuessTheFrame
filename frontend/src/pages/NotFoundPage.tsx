import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { Button } from '../components/ui'

export function NotFoundPage() {
  return (
    <section className="mx-auto grid min-h-[60svh] w-full max-w-3xl place-items-center px-4 py-16 text-center">
      <div>
        <div className="font-display text-8xl leading-none text-gold-400">404</div>
        <h1 className="mt-4 font-display text-4xl tracking-wide text-cream-50">
          Cette scène n'existe pas.
        </h1>
        <p className="mt-3 text-sm text-sand-400">
          La page demandée est introuvable ou a été déplacée.
        </p>
        <Link to="/" className="mt-8 inline-block">
          <Button variant="secondary">
            <ArrowLeft size={15} />
            Retour à l'accueil
          </Button>
        </Link>
      </div>
    </section>
  )
}
