import api from './index'

export const listCourses = () => api.get('/knowledge/courses')
export const getCourseTree = (courseId, version) => api.get(`/knowledge/courses/${courseId}/tree`, { params: version ? { version } : {} })
export const searchCourseKnowledge = (courseId, query, options = {}) => api.get(`/knowledge/courses/${courseId}/search`, { params: { q: query, ...options } })
export const getCourseLearningMap = (courseId) => api.get(`/knowledge/courses/${courseId}/learning-map`)
export const getKnowledgePoint = (pointId) => api.get(`/knowledge/points/${pointId}`)
export const getKnowledgePointLearning = (pointId) => api.get(`/knowledge/points/${pointId}/learning`)
export const getKnowledgeMastery = (courseId) => api.get('/knowledge/mastery', { params: { course_id: courseId } })
