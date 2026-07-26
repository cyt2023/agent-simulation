import { createRouter, createWebHistory } from 'vue-router'
import ParticipantLogin from '../views/participant_login.vue'
import ParticipantInterface from '../views/participant.vue'
import ResearcherDashboard from '../views/researcher.vue'
import AnnotationTest from '../views/annotation_test.vue'
import PostSessionAnnotation from '../views/PostSessionAnnotation.vue'
import PostAnnotationLogin from '../views/post_annotation_login.vue'
import Study1Participant from '../study1/views/Study1Participant.vue'
import Study1Researcher from '../study1/views/Study1Researcher.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/',
      redirect: '/login'
    },
    {
      path: '/annotation-test',
      name: 'annotation-test',
      component: AnnotationTest
    },
    {
      path: '/post-annotation-login',
      name: 'post-annotation-login',
      component: PostAnnotationLogin
    },
    {
      path: '/post-annotation',
      name: 'post-session-annotation',
      component: PostSessionAnnotation
    },
    {
      path: '/login',
      name: 'participant-login',
      component: ParticipantLogin
    },
    {
      path: '/participant',
      name: 'participant-interface',
      component: ParticipantInterface,
      meta: { requiresAuth: true }
    },
    {
      path: '/researcher',
      name: 'researcher-dashboard',
      component: ResearcherDashboard
    },
    {
      path: '/study1/join/:token',
      name: 'study1-join',
      component: Study1Participant
    },
    {
      path: '/study1/participant',
      name: 'study1-participant',
      component: Study1Participant,
      meta: { requiresStudy1Auth: true }
    },
    {
      path: '/researcher/study1',
      name: 'study1-researcher',
      component: Study1Researcher
    }
  ]
})

// Navigation guard to check authentication for participant interface only
router.beforeEach((to, from, next) => {
  if (to.matched.some(record => record.meta.requiresStudy1Auth)) {
    const study1Token = sessionStorage.getItem('study1_auth_token')
    if (!study1Token) {
      next('/')
    } else {
      next()
    }
    return
  }
  if (to.matched.some(record => record.meta.requiresAuth)) {
    const authToken = sessionStorage.getItem('auth_token')
    if (!authToken) {
      next('/login')
    } else {
      next()
    }
  } else {
    next()
  }
})

export default router
